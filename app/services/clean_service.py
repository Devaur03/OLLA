"""
PURPOSE: Clean raw markdown/text from Jina Reader into dense,
coherent plain text suitable for chunking and ranking.

Cleaning steps (in order):
1. Unicode normalization (NFKC)
2. Remove markdown syntax artifacts (images, headers, code blocks, etc.)
3. Clean up hyperlinks (keep anchor text, remove URL)
4. Remove boilerplate patterns (cookie notices, newsletter prompts, etc.)
5. Collapse excessive whitespace
6. Strip leading/trailing whitespace
"""

import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

# Common boilerplate patterns found on most web pages
# These are removed because they add noise without informational value
BOILERPLATE_PATTERNS = [
    r"cookie\s+(policy|notice|consent|preferences)[\s\S]{0,200}",
    r"accept\s+all\s+cookies[\s\S]{0,100}",
    r"we\s+use\s+cookies[\s\S]{0,200}",
    r"subscribe\s+to\s+(our\s+)?newsletter[\s\S]{0,200}",
    r"sign\s+up\s+for\s+(our\s+)?newsletter[\s\S]{0,200}",
    r"all\s+rights\s+reserved[\s\S]{0,100}",
    r"©\s*\d{4}[\s\S]{0,100}",
    r"privacy\s+policy[\s\S]{0,50}",
    r"terms\s+of\s+service[\s\S]{0,50}",
    r"advertisement[\s\S]{0,50}",
    r"sponsored\s+content[\s\S]{0,50}",
    r"share\s+(this\s+)?(article|post|page)[\s\S]{0,100}",
    r"follow\s+us\s+on[\s\S]{0,100}",
    r"related\s+articles[\s\S]{0,50}",
    r"you\s+might\s+also\s+like[\s\S]{0,50}",
]


class CleanService:
    """
    Cleans raw markdown text into clean prose suitable for RAG chunking.
    All methods are pure functions — no state, safe for concurrent use.
    """

    def clean(self, raw: str) -> str:
        """
        Run the full cleaning pipeline on raw text.

        Args:
            raw: Raw text/markdown from Jina Reader.

        Returns:
            Cleaned plain text. Returns empty string if input is empty or
            becomes empty after cleaning.
        """
        if not raw or not raw.strip():
            return ""

        text = raw

        # Step 1: Normalize unicode characters
        text = self._normalize_unicode(text)

        # Step 2: Remove markdown image syntax entirely (no useful text)
        text = self._remove_images(text)

        # Step 3: Remove code blocks (inline and fenced) — usually not useful for RAG
        text = self._remove_code_blocks(text)

        # Step 4: Convert hyperlinks to just their anchor text
        text = self._clean_links(text)

        # Step 5: Remove markdown headers (keep the text, remove ## symbols)
        text = self._remove_headers(text)

        # Step 6: Remove bold/italic markers (keep the text)
        text = self._remove_emphasis(text)

        # Step 7: Remove bullet list markers
        text = self._remove_list_markers(text)

        # Step 8: Remove table formatting
        text = self._remove_tables(text)

        # Step 9: Remove boilerplate
        text = self._remove_boilerplate(text)

        # Step 10: Collapse whitespace
        text = self._collapse_whitespace(text)

        result = text.strip()
        logger.debug(f"CleanService: {len(raw)} chars → {len(result)} chars after cleaning")
        return result

    # --- Private cleaning methods ---

    def _normalize_unicode(self, text: str) -> str:
        """NFKC normalization: converts ligatures, compatibility chars, etc."""
        return unicodedata.normalize("NFKC", text)

    def _remove_images(self, text: str) -> str:
        """Remove markdown image syntax: ![alt text](url)"""
        return re.sub(r"!\[.*?\]\(.*?\)", "", text, flags=re.DOTALL)

    def _remove_code_blocks(self, text: str) -> str:
        """Remove fenced code blocks (```...```) and inline code (`...`)."""
        # Fenced blocks first
        text = re.sub(r"```[\s\S]*?```", "", text)
        # Then inline code
        text = re.sub(r"`[^`\n]+`", "", text)
        return text

    def _clean_links(self, text: str) -> str:
        """
        Convert [anchor text](url) to just 'anchor text'.
        Also handles bare URLs by removing them.
        """
        # Markdown links: keep anchor text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
        # Bare URLs: remove entirely
        text = re.sub(r"https?://\S+", "", text)
        return text

    def _remove_headers(self, text: str) -> str:
        """Remove markdown header markers (## etc) but keep the header text."""
        return re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    def _remove_emphasis(self, text: str) -> str:
        """Remove **bold** and *italic* markers but keep text content."""
        # Bold (** or __)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"__(.+?)__", r"\1", text, flags=re.DOTALL)
        # Italic (* or _)
        text = re.sub(r"\*(.+?)\*", r"\1", text, flags=re.DOTALL)
        text = re.sub(r"_(.+?)_", r"\1", text, flags=re.DOTALL)
        # Strikethrough
        text = re.sub(r"~~(.+?)~~", r"\1", text, flags=re.DOTALL)
        return text

    def _remove_list_markers(self, text: str) -> str:
        """Remove bullet/list markers (-, *, >) at line starts."""
        return re.sub(r"^\s*[-*>]\s+", "", text, flags=re.MULTILINE)

    def _remove_tables(self, text: str) -> str:
        """Remove markdown table formatting (pipes and dashes)."""
        # Remove table separator rows (|---|---|)
        text = re.sub(r"^\s*\|[-:\s|]+\|\s*$", "", text, flags=re.MULTILINE)
        # Remove pipe characters from table rows
        text = re.sub(r"\|", " ", text)
        return text

    def _remove_boilerplate(self, text: str) -> str:
        """Remove common web page boilerplate text."""
        for pattern in BOILERPLATE_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)
        return text

    def _collapse_whitespace(self, text: str) -> str:
        """
        Normalize whitespace:
        - Max 2 consecutive newlines (1 blank line between paragraphs)
        - Max 1 space between words
        - Remove trailing whitespace per line
        """
        # Remove trailing spaces on each line
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
        # Collapse 3+ newlines to 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces to one
        text = re.sub(r" {2,}", " ", text)
        return text
