"""
PURPOSE: RAG answer synthesis — turn retrieved chunks into a real answer.

Instead of handing the caller raw text + chunks, this service feeds the
top-ranked results to a local LLM (Ollama) and asks it to write a clear,
directly-useful answer to the user's question, with inline [n] source
citations.

Ollama is fully local (http://localhost:11434) — no API key, no data leaves
the machine. If Ollama is not running, the service degrades gracefully: the
search still returns results, just without a synthesized answer.

Run a model first, e.g.:   ollama pull llama3.2

IMPORTANT (proxy): the HTTP client is created with trust_env=False so that an
HTTP_PROXY / HTTPS_PROXY / ALL_PROXY environment variable cannot hijack the
localhost call to Ollama. Routing a localhost request through a proxy is what
caused the silent 120s timeout.
"""

import logging

import httpx

from app.config import settings
from app.models.response import SearchResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a precise research assistant. Answer the user's question using "
    "ONLY the numbered sources provided. Cite every claim inline with its "
    "source number in square brackets, e.g. [1] or [2]. Write a clear, "
    "well-structured answer in plain language that directly addresses the "
    "question — not a summary of each source. If the sources do not contain "
    "enough information to answer, say so honestly. Do not invent facts or "
    "cite sources that were not provided."
)


class AnswerResult:
    """Outcome of an answer-synthesis attempt."""

    def __init__(self, answer: str = "", model: str = "", ok: bool = False, error: str = ""):
        self.answer = answer
        self.model = model
        self.ok = ok
        self.error = error


class AnswerService:
    """Synthesizes a cited natural-language answer from retrieved results."""

    def __init__(self, model: str | None = None) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        # Per-request override (Phase 3) falls back to the configured model.
        self.model = model or settings.ollama_model
        self.enabled = settings.enable_answer_synthesis
        self.timeout = settings.ollama_timeout
        self.max_context_chars = settings.answer_max_context_chars
        self.num_predict = settings.ollama_num_predict

    def _client(self) -> httpx.AsyncClient:
        """
        HTTP client for Ollama.

        - trust_env=False: ignore HTTP(S)_PROXY / ALL_PROXY env vars so a
          system/corporate proxy cannot black-hole the localhost request.
        - short connect timeout: if Ollama is down, fail in ~5s instead of
          blocking the whole search until the read timeout.
        """
        return httpx.AsyncClient(
            trust_env=False,
            timeout=httpx.Timeout(connect=5.0, read=self.timeout, write=15.0, pool=5.0),
        )

    async def synthesize(self, query: str, results: list[SearchResult]) -> AnswerResult:
        """
        Build a RAG answer for `query` from `results`. Never raises — on any
        failure it returns an AnswerResult with ok=False so the pipeline can
        degrade gracefully.
        """
        if not self.enabled:
            return AnswerResult(error="answer synthesis disabled")
        if not results:
            return AnswerResult(error="no results to synthesize from")

        context = self._build_context(results)
        user_prompt = (
            f"Question: {query}\n\n"
            f"Sources:\n{context}\n\n"
            f"Write the answer to the question now, citing sources inline as [n]."
        )

        try:
            async with self._client() as client:
                resp = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": _SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        # keep the model resident so later searches are fast
                        "keep_alive": "10m",
                        "options": {
                            "temperature": 0.2,
                            "num_predict": self.num_predict,
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            answer = (data.get("message", {}) or {}).get("content", "").strip()
            if not answer:
                return AnswerResult(model=self.model, error="LLM returned an empty answer")
            logger.info(
                "AnswerService: synthesized answer via %s (%d chars)", self.model, len(answer)
            )
            return AnswerResult(answer=answer, model=self.model, ok=True)

        except httpx.ConnectError:
            msg = (
                f"Ollama not reachable at {self.base_url}. Start it "
                f"(`ollama serve`) and pull a model: `ollama pull {self.model}`."
            )
            logger.warning("AnswerService: %s", msg)
            return AnswerResult(model=self.model, error=msg)
        except httpx.TimeoutException:
            msg = (
                f"Ollama did not respond within {self.timeout:.0f}s. The first "
                f"request loads the model and is slow — try the search again "
                f"(the model stays warm). If it keeps timing out, raise "
                f"OLLAMA_TIMEOUT in .env or use a smaller model."
            )
            logger.warning("AnswerService: %s", msg)
            return AnswerResult(model=self.model, error=msg)
        except httpx.HTTPStatusError as e:
            detail = ""
            try:
                detail = e.response.text[:200]
            except Exception:  # noqa: BLE001
                pass
            if e.response.status_code == 404:
                detail = (
                    f"model '{self.model}' not found — run `ollama pull {self.model}`. {detail}"
                )
            msg = f"Ollama HTTP {e.response.status_code}: {detail}"
            logger.warning("AnswerService: %s", msg)
            return AnswerResult(model=self.model, error=msg)
        except Exception as e:  # noqa: BLE001
            # Never let the error be blank — some httpx errors stringify empty.
            msg = str(e) or repr(e) or type(e).__name__
            logger.warning("AnswerService: synthesis failed: %s", msg)
            return AnswerResult(model=self.model, error=msg)

    async def ping(self) -> AnswerResult:
        """
        Lightweight connectivity check — confirms Ollama is up and the
        configured model is available. Used by diagnostics.
        """
        try:
            async with self._client() as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                tags = resp.json().get("models", [])
            names = {m.get("name", "").split(":")[0] for m in tags}
            if self.model.split(":")[0] not in names:
                return AnswerResult(
                    model=self.model,
                    error=f"Ollama is up but model '{self.model}' is not pulled. "
                    f"Run: ollama pull {self.model}",
                )
            return AnswerResult(
                model=self.model, ok=True, answer=f"Ollama OK — {len(tags)} model(s) available"
            )
        except httpx.ConnectError:
            return AnswerResult(model=self.model, error=f"Ollama not reachable at {self.base_url}")
        except Exception as e:  # noqa: BLE001
            return AnswerResult(model=self.model, error=str(e) or repr(e))

    def _build_context(self, results: list[SearchResult]) -> str:
        """Number the results and pack their content within the char budget."""
        blocks: list[str] = []
        budget = self.max_context_chars
        for i, r in enumerate(results, start=1):
            if budget <= 0:
                break
            snippet = (r.content or "").strip()
            # Give each source a fair slice of the remaining budget.
            per_source = max(400, budget // max(1, len(results) - i + 1))
            snippet = snippet[:per_source]
            budget -= len(snippet)
            blocks.append(f"[{i}] {r.title}\nURL: {r.url}\n{snippet}")
        return "\n\n".join(blocks)
