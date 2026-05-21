"""ContentProcessor: clean + chunk pipeline (pure domain logic, no external I/O)."""
import re
import logging
from app.domain.models.search import Chunk

logger = logging.getLogger(__name__)


class ContentProcessor:
    """Cleans raw markdown and splits it into RAG-ready chunks.

    This class has zero external dependencies — it can be tested without
    any network calls, databases, or configuration.

    Example:
        >>> proc = ContentProcessor(chunk_size=500, overlap=50)
        >>> chunks = proc.process("Some raw # markdown content...")
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process(self, raw_content: str) -> tuple[str, list[Chunk]]:
        """Clean content and return (cleaned_text, chunks).

        Args:
            raw_content: Raw markdown from the fetcher.

        Returns:
            Tuple of (cleaned_text, list_of_chunks). Both will be empty
            if the content has no meaningful text after cleaning.
        """
        cleaned = self._clean(raw_content)
        if not cleaned:
            return "", []
        chunks = self._chunk(cleaned)
        return cleaned, chunks

    def _clean(self, text: str) -> str:
        """Remove markdown noise, leaving only readable prose."""
        # Remove images
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        # Unwrap links (keep display text)
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Remove headers but keep text
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # Remove fenced code blocks
        text = re.sub(r"```[\s\S]*?```", "", text)
        text = re.sub(r"`[^`\n]+`", "", text)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Remove horizontal rules
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        # Remove bold/italic markers
        text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    def _chunk(self, text: str) -> list[Chunk]:
        """Split cleaned text into overlapping chunks."""
        if not text:
            return []

        # Prefer paragraph boundaries
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
        if not paragraphs:
            return [Chunk(chunk_id=0, text=text[:self.chunk_size],
                          char_count=min(len(text), self.chunk_size))]

        chunks: list[Chunk] = []
        current = ""
        chunk_id = 0

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = (current + "\n\n" + para).strip() if current else para
            else:
                if current:
                    chunks.append(Chunk(chunk_id=chunk_id, text=current,
                                        char_count=len(current)))
                    chunk_id += 1
                    # Keep overlap from end of previous chunk
                    current = current[-self.overlap:].strip() + "\n\n" + para
                    current = current.strip()
                else:
                    current = para

        if current:
            chunks.append(Chunk(chunk_id=chunk_id, text=current, char_count=len(current)))

        return chunks
