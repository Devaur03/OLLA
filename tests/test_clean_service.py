import pytest
from app.services.clean_service import CleanService


@pytest.fixture
def svc():
    return CleanService()


def test_removes_markdown_headers(svc):
    result = svc.clean("## Hello World\nSome content here.")
    assert "##" not in result
    assert "Hello World" in result
    assert "Some content here" in result


def test_removes_images(svc):
    result = svc.clean("Text before ![alt](http://img.com/pic.jpg) text after.")
    assert "![" not in result
    assert "Text before" in result
    assert "text after" in result


def test_cleans_links(svc):
    result = svc.clean("Read [this article](https://example.com) for more info.")
    assert "](https://example.com)" not in result
    assert "this article" in result


def test_removes_code_blocks(svc):
    result = svc.clean("Intro text.\n```python\nprint('hello')\n```\nEnd text.")
    assert "```" not in result
    assert "Intro text" in result
    assert "End text" in result


def test_collapses_whitespace(svc):
    result = svc.clean("Line one\n\n\n\n\nLine two")
    assert "\n\n\n" not in result


def test_returns_empty_for_empty_input(svc):
    assert svc.clean("") == ""
    assert svc.clean("   ") == ""
    assert svc.clean("\n\n\n") == ""
