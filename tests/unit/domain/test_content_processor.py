"""
Unit tests for ContentProcessor.

Pure domain logic — no external dependencies, no async.
"""
import pytest
from app.domain.services.content_processor import ContentProcessor


@pytest.fixture
def proc():
    return ContentProcessor(chunk_size=200, overlap=20)


class TestClean:
    def test_removes_markdown_headers(self, proc):
        cleaned, _ = proc.process("## Hello World\nSome content here.")
        assert "##" not in cleaned
        assert "Hello World" in cleaned

    def test_removes_image_tags(self, proc):
        cleaned, _ = proc.process("Text before ![alt](http://img.com/pic.jpg) text after.")
        assert "![" not in cleaned
        assert "Text before" in cleaned

    def test_unwraps_links_keeping_text(self, proc):
        cleaned, _ = proc.process("Read [this article](https://example.com) for info.")
        assert "](https://example.com)" not in cleaned
        assert "this article" in cleaned

    def test_removes_fenced_code_blocks(self, proc):
        cleaned, _ = proc.process("Intro.\n```python\nprint('hi')\n```\nEnd.")
        assert "```" not in cleaned
        assert "Intro" in cleaned
        assert "End" in cleaned

    def test_collapses_excess_newlines(self, proc):
        cleaned, _ = proc.process("Line one\n\n\n\n\nLine two")
        assert "\n\n\n" not in cleaned

    def test_empty_input_returns_empty(self, proc):
        cleaned, chunks = proc.process("")
        assert cleaned == ""
        assert chunks == []

    def test_whitespace_only_returns_empty(self, proc):
        cleaned, chunks = proc.process("   \n\n  ")
        assert cleaned == ""
        assert chunks == []


class TestChunk:
    def test_short_text_produces_single_chunk(self, proc):
        _, chunks = proc.process("Short text.")
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."

    def test_long_text_produces_multiple_chunks(self, proc):
        # Use multi-paragraph input so the paragraph-boundary splitter activates
        paragraphs = ["This is a sentence that fills a paragraph. " * 3 for _ in range(6)]
        text = "\n\n".join(paragraphs)
        _, chunks = proc.process(text)
        assert len(chunks) > 1

    def test_chunk_ids_are_sequential(self, proc):
        text = "\n\n".join(["Paragraph " + str(i) + ". " * 15 for i in range(8)])
        _, chunks = proc.process(text)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_id == i

    def test_char_count_matches_text_length(self, proc):
        text = "\n\n".join(["Word " * 25 for _ in range(5)])
        _, chunks = proc.process(text)
        for chunk in chunks:
            assert chunk.char_count == len(chunk.text)

    def test_no_chunk_exceeds_chunk_size_significantly(self, proc):
        # Use paragraphs whose individual length stays near chunk_size
        text = "\n\n".join(["Word " * 30 for _ in range(6)])  # ~150 chars each
        _, chunks = proc.process(text)
        # No assembled chunk should be more than 3x chunk_size
        for chunk in chunks:
            assert chunk.char_count <= proc.chunk_size * 3
