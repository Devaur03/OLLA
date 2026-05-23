"""Unit tests for Phase 10 parent-child (hierarchical) chunking."""

from app.services.chunk_service import ChunkService

# Build a long document: many short paragraphs so it spans multiple parents.
DOC = "\n\n".join(f"Paragraph {i} about vector databases and retrieval." * 3
                  for i in range(60))


def test_empty_text_yields_empty_hierarchy():
    h = ChunkService(chunk_size=200).chunk_hierarchical("")
    assert h == {"parents": [], "children": []}


def test_hierarchy_has_parents_and_children():
    h = ChunkService(chunk_size=200, overlap=20).chunk_hierarchical(DOC, parent_size=1000)
    assert len(h["parents"]) >= 2
    assert len(h["children"]) >= len(h["parents"])


def test_parents_are_larger_than_children():
    h = ChunkService(chunk_size=200, overlap=20).chunk_hierarchical(DOC, parent_size=1000)
    avg_parent = sum(p.char_count for p in h["parents"]) / len(h["parents"])
    avg_child = sum(c["chunk"].char_count for c in h["children"]) / len(h["children"])
    assert avg_parent > avg_child


def test_every_child_points_at_a_valid_parent():
    h = ChunkService(chunk_size=200).chunk_hierarchical(DOC, parent_size=1000)
    n_parents = len(h["parents"])
    for child in h["children"]:
        assert 0 <= child["parent_index"] < n_parents


def test_child_ids_are_sequential_and_unique():
    h = ChunkService(chunk_size=200).chunk_hierarchical(DOC, parent_size=1000)
    ids = [c["chunk"].chunk_id for c in h["children"]]
    assert ids == list(range(len(ids)))


def test_short_text_is_one_parent_one_child():
    h = ChunkService(chunk_size=500).chunk_hierarchical("a short document.", parent_size=2000)
    assert len(h["parents"]) == 1
    assert len(h["children"]) == 1
    assert h["children"][0]["parent_index"] == 0
