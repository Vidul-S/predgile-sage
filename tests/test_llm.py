import pytest
from unittest.mock import patch, MagicMock
from src.answer_generator import AnswerGenerator


@pytest.fixture
def generator():
    return AnswerGenerator()


def test_ollama_prompt_construction(generator):
    """Test that question, chunks, dates, and conflict resolutions are formatted in the prompt."""
    query = "What is the API rate limit on the Pro plan?"
    chunks = [
        {"doc_id": "api-rate-limits.md", "date": "2026-02-09", "text": "Pro: 1,000 req/min.", "status_label": "[AUTHORITATIVE]"}
    ]
    conflicts = [{"topic": "Rate Limit", "active_rule": "1,000 req/min", "resolution": "Raised from 500 to 1,000"}]
    
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "The Pro plan API rate limit is 1,000 requests per minute."}}
        mock_post.return_value = mock_resp

        res = generator.generate(query, chunks, conflicts=conflicts)
        assert mock_post.called
        sent_payload = mock_post.call_args[1]["json"]
        user_content = sent_payload["messages"][1]["content"]
        assert "CUSTOMER QUESTION" in user_content
        assert "RETRIEVED EVIDENCE" in user_content
        assert "DETECTED CONFLICTS" in user_content


def test_successful_llm_answer_generation(generator):
    """Verifies parsing and response handling from mock Ollama API."""
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "The file attachment limit is 10 MB."}}
        mock_post.return_value = mock_resp

        chunks = [{"doc_id": "invoice-attachments.md", "text": "10 MB maximum", "date": "2025-09-20"}]
        res = generator.generate("What is the invoice limit?", chunks)
        assert res["status"] == "answered"
        assert res["llm_generated"] is True
        assert "10 MB" in res["answer"]


def test_ollama_connection_failure_and_fallback(generator):
    """Verifies graceful fallback and accurate error reporting when Ollama is offline."""
    with patch("requests.post", side_effect=Exception("Connection refused")):
        chunks = [{"doc_id": "invoice-attachments.md", "text": "10 MB maximum per file", "date": "2025-09-20"}]
        res = generator.generate("What is the maximum file size for invoice attachments?", chunks)
        assert res["status"] == "answered"
        assert res["llm_generated"] is False
        assert "10 MB" in res["answer"]
        assert res["model"] == "deterministic-fallback"
        assert "Connection refused" in res["llm_error"]


def test_llm_insufficient_evidence_cryptocurrency(generator):
    """Verifies honest refusal on unsupported topics like cryptocurrency."""
    res = generator.generate("What is the refund window for cryptocurrency payments?", [])
    assert res["status"] == "abstained"
    assert res["status_label"] == "Insufficient evidence"
    assert res["answer"] is None


def test_llm_ambiguous_query_clarification(generator):
    """Verifies ambiguity detection and clarification request for under-specified questions."""
    res = generator.generate("How long do payouts take?", [])
    assert res["status"] == "clarify"
    assert res["status_label"] == "Needs clarification"
    assert "clarification_prompt" in res
    assert "plan tier" in res["clarification_prompt"].lower()


def test_llm_conflict_resolution_context(generator):
    """Verifies that conflict analysis is included in the LLM context."""
    conflicts = [{"topic": "V1 Deprecation", "resolution": "Removed on 2026-01-15"}]
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "Endpoint removed."}}
        mock_post.return_value = mock_resp

        generator.generate("Can I use /v1/charges?", [{"doc_id": "changelog.md", "text": "410 gone"}], conflicts=conflicts)
        user_content = mock_post.call_args[1]["json"]["messages"][1]["content"]
        assert "Removed on 2026-01-15" in user_content
