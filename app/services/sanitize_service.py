"""
PURPOSE: Defend the RAG pipeline against prompt injection (COMPARISON_README §9).

Scraped web content flows straight into chunks and then into downstream LLM
agents. A malicious page can embed text like "Ignore all previous instructions
and ..." which an agent may then obey. This service strips instruction-like
patterns from scraped content *before* it is chunked and stored.

This is a defence-in-depth measure, not a guarantee — it neutralises the common,
well-known injection phrasings while leaving legitimate prose intact.
"""

import logging
import re

logger = logging.getLogger(__name__)

_REDACTION = " [redacted: instruction-like text removed] "

# Each pattern targets a well-known prompt-injection phrasing. Patterns are
# deliberately conservative: they match imperative instruction framing, not
# ordinary sentences that happen to contain these words.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+"
               r"(instructions?|prompts?|context|messages?)[^.\n]*", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier|"
               r"system)\s+(instructions?|prompts?|messages?)[^.\n]*", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|what)\s+(you|i)\s+"
               r"(were\s+told|said|know)[^.\n]*", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the|in)\b[^.\n]*", re.IGNORECASE),
    re.compile(r"(new|updated|revised)\s+(system\s+)?(instructions?|prompt|rules?)\s*:"
               r"[^.\n]*", re.IGNORECASE),
    re.compile(r"(reveal|print|repeat|show|output)\s+(your|the)\s+"
               r"(system\s+prompt|instructions?|prompt)[^.\n]*", re.IGNORECASE),
    re.compile(r"do\s+not\s+(follow|obey|listen\s+to)\s+"
               r"(the\s+)?(previous|prior|system|original)[^.\n]*", re.IGNORECASE),
    re.compile(r"\[?\s*(system|assistant|developer)\s*\]?\s*:\s*you\s+(must|should|will)"
               r"[^.\n]*", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+(are|were)\s+)?(an?\s+)?"
               r"(unrestricted|jailbroken|dan|uncensored)[^.\n]*", re.IGNORECASE),
    re.compile(r"<\s*/?\s*(system|instruction|prompt)\s*>", re.IGNORECASE),
]


class SanitizeService:
    """Strips prompt-injection patterns from scraped text. Pure / stateless."""

    def sanitize(self, text: str) -> tuple[str, int]:
        """
        Returns (cleaned_text, num_patterns_removed).

        A non-zero count is worth logging/tracing — it means a fetched page
        contained instruction-like content.
        """
        if not text:
            return "", 0

        removed = 0
        cleaned = text
        for pattern in _INJECTION_PATTERNS:
            cleaned, n = pattern.subn(_REDACTION, cleaned)
            removed += n

        if removed:
            # Collapse any redaction runs the substitution may have created.
            cleaned = re.sub(
                r"(\s*\[redacted: instruction-like text removed\]\s*)+",
                _REDACTION, cleaned,
            )
            logger.warning(
                "SanitizeService: redacted %d instruction-like span(s) from scraped content",
                removed,
            )
        return cleaned, removed
