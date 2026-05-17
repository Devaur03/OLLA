from datetime import date
from app.models.response import SearchResult
import logging

logger = logging.getLogger(__name__)


class CitationService:
    """Generates formatted citations in multiple styles."""

    def generate_apa(self, result: SearchResult) -> str:
        """APA style citation."""
        today = date.today().strftime("%Y, %B %d")
        title = result.title or result.url
        return f"{title}. (n.d.). Retrieved {today}, from {result.url}"

    def generate_markdown_link(self, result: SearchResult) -> str:
        """Markdown hyperlink citation."""
        title = result.title or result.url
        return f"[{title}]({result.url})"

    def generate_citations_block(self, results: list[SearchResult]) -> str:
        """
        Generate a full citations section in markdown format.
        Suitable for appending to agent-generated content.
        """
        if not results:
            return ""

        lines = ["## Sources\n"]
        for i, result in enumerate(results, 1):
            title = result.title or result.url
            today = date.today().strftime("%Y-%m-%d")
            lines.append(
                f"{i}. [{title}]({result.url}) "
                f"— Relevance: {result.score:.2f} "
                f"— Retrieved: {today}"
            )

        return "\n".join(lines)

    def generate_json_citations(self, results: list[SearchResult]) -> list[dict]:
        """
        Generate machine-readable citation objects.
        Useful for agents that need to process citations programmatically.
        """
        today = date.today().isoformat()
        return [
            {
                "rank": result.rank,
                "title": result.title,
                "url": result.url,
                "score": result.score,
                "retrieved_date": today,
                "apa": self.generate_apa(result),
                "markdown": self.generate_markdown_link(result),
            }
            for result in results
        ]
