import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

DOMAIN_CREDIBILITY: dict[str, float] = {
    # Academic & research
    "arxiv.org": 0.95,
    "scholar.google.com": 0.95,
    "pubmed.ncbi.nlm.nih.gov": 0.95,
    "nature.com": 0.95,
    "ieee.org": 0.92,
    "acm.org": 0.92,

    # Official documentation
    "docs.python.org": 0.95,
    "docs.microsoft.com": 0.92,
    "developer.mozilla.org": 0.95,
    "kubernetes.io": 0.92,
    "docs.docker.com": 0.92,
    "fastapi.tiangolo.com": 0.90,
    "docs.sqlalchemy.org": 0.90,
    "docs.pydantic.dev": 0.90,
    "redis.io": 0.90,
    "postgresql.org": 0.90,

    # Established references
    "wikipedia.org": 0.80,
    "github.com": 0.85,
    "stackoverflow.com": 0.82,

    # Quality tech blogs
    "aws.amazon.com": 0.88,
    "cloud.google.com": 0.88,
    "azure.microsoft.com": 0.88,
    "openai.com": 0.88,
    "anthropic.com": 0.88,
    "huggingface.co": 0.85,
    "towardsdatascience.com": 0.70,
    "medium.com": 0.60,
    "dev.to": 0.65,
    "hashnode.com": 0.62,

    # Lower credibility
    "reddit.com": 0.50,
    "quora.com": 0.45,
}


class CredibilityService:
    """
    Assigns domain-based credibility scores to URLs.
    """

    def score(self, url: str) -> float:
        """
        Returns credibility score (0.0–1.0) for a URL.

        Args:
            url: Full URL string.

        Returns:
            Float between 0.0 and 1.0. Default 0.5 for unknown domains.
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Strip www. prefix
            if domain.startswith("www."):
                domain = domain[4:]

            # Exact match first
            if domain in DOMAIN_CREDIBILITY:
                return DOMAIN_CREDIBILITY[domain]

            # Partial match (e.g. sub.stackoverflow.com)
            for known_domain, score in DOMAIN_CREDIBILITY.items():
                if domain.endswith(f".{known_domain}"):
                    return score

            return 0.5  # Unknown domain default

        except Exception:
            return 0.5
