import math, re, logging
from app.domain.models.search import RankedResult

logger = logging.getLogger(__name__)

DOMAIN_SCORES = {
    "arxiv.org": 0.95, "nature.com": 0.95, "docs.python.org": 0.95,
    "developer.mozilla.org": 0.95, "ieee.org": 0.92, "docs.microsoft.com": 0.92,
    "kubernetes.io": 0.92, "docs.docker.com": 0.92, "fastapi.tiangolo.com": 0.90,
    "docs.sqlalchemy.org": 0.90, "docs.pydantic.dev": 0.90, "redis.io": 0.90,
    "postgresql.org": 0.90, "github.com": 0.85, "huggingface.co": 0.85,
    "wikipedia.org": 0.80, "stackoverflow.com": 0.82, "aws.amazon.com": 0.88,
    "cloud.google.com": 0.88, "openai.com": 0.88, "anthropic.com": 0.88,
    "towardsdatascience.com": 0.70, "medium.com": 0.60, "dev.to": 0.65,
    "reddit.com": 0.50, "quora.com": 0.45,
}
DEFAULT_CREDIBILITY = 0.55


class RankingEngine:
    def rank(self, query, items):
        if not items:
            return []
        query_tokens = self._tok(query)
        all_docs = [c for _, _, c, _ in items]
        scored = []
        for pos, (title, url, content, chunks) in enumerate(items, 1):
            rel = self._tfidf(query_tokens, content, all_docs)
            cred = self._cred(url)
            scored.append(RankedResult(
                rank=pos, title=title, url=url, content=content, chunks=chunks,
                score=round(rel * 0.7 + cred * 0.3, 4),
                char_count=len(content), chunk_count=len(chunks),
            ))
        scored.sort(key=lambda r: r.score, reverse=True)
        for i, r in enumerate(scored, 1):
            r.rank = i
        return scored

    def _tfidf(self, query_tokens, doc, corpus):
        if not query_tokens or not doc:
            return 0.0
        dtok = self._tok(doc)
        if not dtok:
            return 0.0
        n = len(corpus)
        score = 0.0
        for term in query_tokens:
            tf = dtok.count(term) / len(dtok)
            df = sum(1 for d in corpus if term in self._tok(d))
            score += tf * (math.log((n + 1) / (df + 1)) + 1.0)
        return min(score / (len(query_tokens) + 1), 1.0)

    def _cred(self, url):
        from urllib.parse import urlparse
        try:
            host = urlparse(url).netloc.lower().lstrip('www.')
            for domain, score in DOMAIN_SCORES.items():
                if host == domain or host.endswith('.' + domain):
                    return score
        except Exception:
            pass
        return DEFAULT_CREDIBILITY

    @staticmethod
    def _tok(text):
        return re.findall(r'[a-z0-9]+', text.lower())
