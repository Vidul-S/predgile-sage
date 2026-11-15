import pytest
from src.document_loader import DocumentLoader
from src.chunker import DocumentChunker


@pytest.fixture(scope="module")
def chunker():
    loader = DocumentLoader()
    docs = loader.load_all()
    c = DocumentChunker(docs)
    c.chunk_all()
    return c


def test_chunker_generates_deduplicated_chunks(chunker):
    """Test chunker generates non-empty set of deduplicated chunks."""
    assert len(chunker.chunks) >= 180
    hashes = [c["md5"] for c in chunker.chunks]
    assert len(hashes) == len(set(hashes))  # No duplicate hashes


def test_chunker_specializes_changelog_partitions(chunker):
    """Test that changelog.md is partitioned into date-stamped entries."""
    changelog_chunks = [c for c in chunker.chunks if c["doc_id"] == "changelog.md"]
    assert len(changelog_chunks) >= 15
    dates = [c["date"] for c in changelog_chunks if c["heading"] != "Introduction"]
    assert all(len(d) == 10 for d in dates)  # YYYY-MM-DD format


def test_chunker_specializes_csv_plan_limits(chunker):
    """Test that plan-limits.csv is partitioned into plan tiers."""
    plan_chunks = [c for c in chunker.chunks if c["doc_id"] == "plan-limits.csv"]
    assert len(plan_chunks) == 3
    plan_names = {c["heading"] for c in plan_chunks}
    assert "Plan: Starter" in plan_names
    assert "Plan: Pro" in plan_names
    assert "Plan: Scale" in plan_names


def test_chunker_preserves_internal_classification(chunker):
    """Test that internal documents retain internal access flag across chunks."""
    internal_chunks = [c for c in chunker.chunks if c["access"] == "internal"]
    assert len(internal_chunks) >= 2
    for c in internal_chunks:
        assert c["doc_id"].startswith("internal-")
