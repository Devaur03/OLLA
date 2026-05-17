import pytest
from app.services.chunk_service import ChunkService


@pytest.fixture
def svc():
    return ChunkService(chunk_size=100, overlap=10)


def test_single_chunk_for_short_text(svc):
    text = "Short text."
    chunks = svc.chunk(text)
    assert len(chunks) == 1
    assert chunks[0].chunk_id == 0
    assert chunks[0].text == "Short text."


def test_multiple_chunks_for_long_text(svc):
    # Create text longer than chunk_size
    text = "This is a sentence. " * 20  # 400 chars
    chunks = svc.chunk(text)
    assert len(chunks) > 1


def test_chunk_ids_are_sequential(svc):
    text = "\n\n".join(["Paragraph number " + str(i) + ". " * 10 for i in range(10)])
    chunks = svc.chunk(text)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == i


def test_char_count_matches_text_length(svc):
    text = "\n\n".join(["Word " * 30 for _ in range(5)])
    chunks = svc.chunk(text)
    for chunk in chunks:
        assert chunk.char_count == len(chunk.text)


def test_empty_input_returns_empty_list(svc):
    assert svc.chunk("") == []
    assert svc.chunk("   ") == []
