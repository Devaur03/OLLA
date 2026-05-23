"""
PURPOSE: Source diversity for result sets (Phase 10).

A retrieval set where four of the top five chunks come from one domain gives a
narrow, possibly biased answer. `DiversityService.diversify()` re-orders a
ranked list so domains are spread out — it keeps each result's relative rank
but caps how many can come from the same domain before others get a turn.

It is a stable round-robin: walk the ranked list, emit a result only if its
domain has not yet hit the per-domain cap for the current pass, then loosen the
cap and pass again until everything is placed. Highest-ranked items still come
first; the only change is that a domain monopoly gets broken up.

Works on plain dicts or any object exposing a `url` attribute.
"""

import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _url_of(item) -> str:
    if isinstance(item, dict):
        return item.get("url", "") or ""
    return getattr(item, "url", "") or ""


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:  # noqa: BLE001
        return (url or "").lower()


class DiversityService:
    """Re-orders a ranked result list to spread sources across domains."""

    def diversify(self, results: list, max_per_domain: int = 2) -> list:
        """
        Return `results` re-ordered for domain diversity.

        `max_per_domain` is the soft cap per round: in the first pass each
        domain may contribute that many results, then the cap relaxes so any
        remainder is still returned (nothing is dropped).
        """
        if max_per_domain < 1 or len(results) <= max_per_domain:
            return list(results)

        remaining = list(results)
        ordered: list = []
        cap = max_per_domain
        while remaining:
            counts: dict[str, int] = {}
            leftovers: list = []
            for item in remaining:
                d = _domain(_url_of(item))
                if counts.get(d, 0) < cap:
                    ordered.append(item)
                    counts[d] = counts.get(d, 0) + 1
                else:
                    leftovers.append(item)
            if len(leftovers) == len(remaining):
                # No progress (every domain already at cap) — relax and retry.
                cap += max_per_domain
                continue
            remaining = leftovers
        return ordered

    def domain_spread(self, results: list) -> dict[str, int]:
        """Count results per domain — handy for traces / dashboards."""
        spread: dict[str, int] = {}
        for item in results:
            d = _domain(_url_of(item))
            spread[d] = spread.get(d, 0) + 1
        return spread
