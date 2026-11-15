import pytest
from src.retriever import HybridRetriever
from src.source_evaluator import SourceEvaluator


@pytest.fixture(scope="module")
def setup_evaluator():
    retriever = HybridRetriever(chunks_path="data/chunks.json")
    evaluator = SourceEvaluator()
    return retriever, evaluator


def test_source_tier_classification(setup_evaluator):
    _, evaluator = setup_evaluator
    assert evaluator.classify_source_tier({"doc_id": "changelog.md", "format": "md"}) == "changelog"
    assert evaluator.classify_source_tier({"doc_id": "refunds-issue.md", "format": "md"}) == "formal_doc"
    assert evaluator.classify_source_tier({"doc_id": "forum-payout-times.txt", "format": "txt"}) == "community_forum"
    assert evaluator.classify_source_tier({"doc_id": "internal-playbook.txt", "access": "internal"}) == "internal"


def test_recency_and_authority_scoring(setup_evaluator):
    _, evaluator = setup_evaluator
    # Newer changelog should have higher authority than older forum post
    cl = evaluator.evaluate_authority({"doc_id": "changelog.md", "date": "2026-04-15", "format": "md"})
    forum = evaluator.evaluate_authority({"doc_id": "forum-test.txt", "date": "2023-01-01", "format": "txt"})
    assert cl["authority_score"] > forum["authority_score"]


def test_rate_limit_conflict_detection(setup_evaluator):
    retriever, evaluator = setup_evaluator
    q = "What is the API rate limit on the Pro plan?"
    chunks = retriever.retrieve(q, top_k=6)
    reranked, conflicts = evaluator.detect_and_resolve_conflicts(q, chunks)
    assert len(conflicts) >= 1
    assert any("Pro Plan API Rate Limit" in c.get("topic", "") for c in conflicts)


def test_attachment_size_conflict_detection(setup_evaluator):
    retriever, evaluator = setup_evaluator
    q = "What is the maximum file size for invoice attachments?"
    chunks = retriever.retrieve(q, top_k=6)
    reranked, conflicts = evaluator.detect_and_resolve_conflicts(q, chunks)
    assert len(conflicts) >= 1
    assert any("Invoice Attachment" in c.get("topic", "") for c in conflicts)


def test_v1_charges_conflict_detection(setup_evaluator):
    retriever, evaluator = setup_evaluator
    q = "Can I still use the /v1/charges endpoint?"
    chunks = retriever.retrieve(q, top_k=6)
    reranked, conflicts = evaluator.detect_and_resolve_conflicts(q, chunks)
    assert len(conflicts) >= 1
    assert any("/v1/charges" in c.get("topic", "") for c in conflicts)
