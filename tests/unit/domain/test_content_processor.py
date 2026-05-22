"""
Unit tests for content processing — CleanService and ChunkService.

(File kept under its original path; it now covers the live services that
replaced the archived ContentProcessor.)
"""
from app.services.chunk_service import ChunkService
from app.services.clean_service import CleanService


def test_clean_strips_markdown_syntax():
    cleaned = CleanService().clean(
        "# Heading\n\n**Bold** and *italic* with a [link](http://x.com).\n\n```code```"
    )
    assert "#" not in cleaned
    assert "**" not in cleaned
    assert "```" not in cleaned
    assert "link" in cleaned  # anchor text is kept


def test_clean_empty_input_returns_empty():
    assert CleanService().clean("") == ""
    assert CleanService().clean("   ") == ""


def test_chunk_splits_long_text_with_sequential_ids():
    text = ("Sentence about vector search and retrieval pipelines. " * 60).strip()
    chunks = ChunkService(chunk_size=200, overlap=30).chunk(text)
    assert len(chunks) > 1
    assert [c.chunk_id for c in chunks] == list(range(len(chunks)))


def test_chunk_short_text_is_single_chunk():
    chunks = ChunkService(chunk_size=500, overlap=50).chunk("short text")
    assert len(chunks) == 1
    assert chunks[0].text == "short text"


def test_chunk_empty_text_returns_empty():
    assert ChunkService().chunk("") == []
