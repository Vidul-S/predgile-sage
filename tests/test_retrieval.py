import pytest
from src.retriever import HybridRetriever


@pytest.fixture(scope="module")
def retriever():
    return HybridRetriever(chunks_path="data/chunks.json")


def test_retrieval_returns_relevant_results(retriever):
    """Test retrieval returns non-empty results for technical questions."""
    results = retriever.retrieve("How do I issue a partial refund?", top_k=5)
    assert len(results) > 0
    assert any("refund" in r["doc_id"].lower() for r in results)


def test_retrieval_preserves_exact_endpoints(retriever):
    """Test tokenizer and exact match boost find exact API path /v1/charges."""
    results = retriever.retrieve("Can I still use the /v1/charges endpoint?", top_k=5)
    doc_ids = [r["doc_id"] for r in results]
    assert any("changelog.md" == d or "charges" in d for d in doc_ids)


def test_retrieval_filters_internal_documents_by_default(retriever):
    """Test that customer queries exclude internal staff files."""
    results = retriever.retrieve("escalation playbook goodwill limits", top_k=10, filter_internal=True)
    for r in results:
        assert r["access"] != "internal"
        assert not r["doc_id"].startswith("internal-")


def test_retrieval_composite_score_ordering(retriever):
    """Test results are properly sorted in descending order of retrieval score."""
    results = retriever.retrieve("What is the API rate limit on the Pro plan?", top_k=6)
    scores = [r["retrieval_score"] for r in results]
    assert scores == sorted(scores, reverse=True)
