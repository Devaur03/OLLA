"""
PURPOSE: Split cleaned text into overlapping chunks for RAG.

Strategy: Paragraph-aware chunking with character-level fallback.
- First tries to respect paragraph boundaries (\n\n)
- Accumulates paragraphs into chunks up to chunk_size
- When a paragraph would overflow the chunk, saves current chunk and starts new one
- Carries the last `overlap` characters into the next chunk for context continuity
- If a single paragraph is larger than chunk_size, splits it at sentence boundaries

Why overlap? Without overlap, a fact that spans a chunk boundary would be split
in half and lost. Overlap ensures each chunk has enough context around its edges.
"""

import re
import logging
from app.models.response import ContentChunk

logger = logging.getLogger(__name__)


class ChunkService:
    """
    Splits cleaned text into overlapping ContentChunk objects.
    Paragraph-aware: respects natural paragraph boundaries where possible.
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        """
        Args:
            chunk_size: Target character length for each chunk.
            overlap: Number of characters to carry from end of previous chunk
                     into the start of the next chunk.
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> list[ContentChunk]:
        """
        Split text into overlapping chunks.

        Args:
            text: Cleaned plain text (output of CleanService).

        Returns:
            List of ContentChunk objects. Returns empty list for empty/short text.
        """
        if not text or not text.strip():
            return []

        # If entire text fits in one chunk, return it directly
        if len(text) <= self.chunk_size:
            return [ContentChunk(chunk_id=0, text=text.strip(), char_count=len(text.strip()))]

        # Split into paragraphs (double newline = paragraph boundary)
        paragraphs = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]

        chunks: list[ContentChunk] = []
        current_text = ""
        chunk_id = 0

        for paragraph in paragraphs:
            # If adding this paragraph keeps us within chunk_size, accumulate it
            prospective = (current_text + "\n\n" + paragraph).strip() if current_text else paragraph

            if len(prospective) <= self.chunk_size:
                current_text = prospective

            else:
                # Save current chunk if it has content
                if current_text:
                    chunks.append(
                        ContentChunk(
                            chunk_id=chunk_id,
                            text=current_text,
                            char_count=len(current_text),
                        )
                    )
                    chunk_id += 1

                    # Build overlap: take last N chars of saved chunk as prefix for next
                    overlap_text = current_text[-self.overlap:] if self.overlap > 0 else ""
                    current_text = (overlap_text + " " + paragraph).strip() if overlap_text else paragraph

                else:
                    # Paragraph itself is larger than chunk_size — split it
                    sub_chunks = self._split_large_paragraph(paragraph, chunk_id)
                    chunks.extend(sub_chunks)
                    chunk_id += len(sub_chunks)

                    # Use last sub-chunk's end as overlap for next paragraph
                    if sub_chunks:
                        last = sub_chunks[-1].text
                        current_text = last[-self.overlap:] if self.overlap > 0 else ""
                    else:
                        current_text = ""

        # Don't forget the last accumulated chunk
        if current_text.strip():
            chunks.append(
                ContentChunk(
                    chunk_id=chunk_id,
                    text=current_text.strip(),
                    char_count=len(current_text.strip()),
                )
            )

        logger.debug(
            f"ChunkService: split {len(text)} chars into {len(chunks)} chunks "
            f"(size={self.chunk_size}, overlap={self.overlap})"
        )
        return chunks

    def chunk_hierarchical(self, text: str, parent_size: int = 2000) -> dict:
        """
        Parent-child chunking (Phase 10).

        Produces two levels:
          - parents:  large `parent_size`-char chunks — wide context handed to
                      the LLM at generation time.
          - children: small `chunk_size`-char chunks split *within* each parent
                      — these are what get embedded and retrieved.

        Returns {"parents": [ContentChunk], "children": [{"chunk": ContentChunk,
        "parent_index": int}]}. Child `chunk_id`s are sequential across the whole
        document; `parent_index` points into the `parents` list.

        Retrieving a small child gives precise matching; expanding to its parent
        gives the LLM enough surrounding context to answer coherently.
        """
        if not text or not text.strip():
            return {"parents": [], "children": []}

        parent_chunker = ChunkService(chunk_size=parent_size, overlap=self.overlap)
        parents = parent_chunker.chunk(text)

        children: list[dict] = []
        child_id = 0
        for parent_index, parent in enumerate(parents):
            for kid in self.chunk(parent.text):
                children.append({
                    "chunk": ContentChunk(
                        chunk_id=child_id,
                        text=kid.text,
                        char_count=kid.char_count,
                    ),
                    "parent_index": parent_index,
                })
                child_id += 1
        return {"parents": parents, "children": children}

    def _split_large_paragraph(self, paragraph: str, start_id: int) -> list[ContentChunk]:
        """
        Fallback: split a paragraph that is larger than chunk_size.
        Tries to split at sentence boundaries (. ! ?) first.
        Falls back to hard character split if no sentence boundaries found.
        """
        chunks: list[ContentChunk] = []
        chunk_id = start_id

        # Try sentence-level splitting
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)

        current = ""
        for sentence in sentences:
            prospective = (current + " " + sentence).strip() if current else sentence

            if len(prospective) <= self.chunk_size:
                current = prospective
            else:
                if current:
                    chunks.append(ContentChunk(
                        chunk_id=chunk_id,
                        text=current,
                        char_count=len(current),
                    ))
                    chunk_id += 1
                    overlap_text = current[-self.overlap:] if self.overlap > 0 else ""
                    current = (overlap_text + " " + sentence).strip() if overlap_text else sentence
                else:
                    # Even a single sentence exceeds chunk_size — hard split
                    for i in range(0, len(sentence), self.chunk_size - self.overlap):
                        segment = sentence[i: i + self.chunk_size]
                        if segment.strip():
                            chunks.append(ContentChunk(
                                chunk_id=chunk_id,
                                text=segment.strip(),
                                char_count=len(segment.strip()),
                            ))
                            chunk_id += 1

        if current.strip():
            chunks.append(ContentChunk(
                chunk_id=chunk_id,
                text=current.strip(),
                char_count=len(current.strip()),
            ))

        return chunks
