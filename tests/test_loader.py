import pytest
from src.document_loader import DocumentLoader


@pytest.fixture(scope="module")
def loader():
    l = DocumentLoader()
    l.load_all()
    return l


def test_loader_ingests_all_150_documents(loader):
    """Test that all 150 documents across all formats are ingested without error."""
    assert len(loader.documents) == 150


def test_loader_covers_all_five_formats(loader):
    """Test that markdown, html, txt, pdf, and csv formats are all successfully parsed."""
    formats = {d["format"] for d in loader.documents}
    assert formats == {"md", "html", "txt", "pdf", "csv"}


def test_loader_extracts_dates_and_titles(loader):
    """Test that metadata like dates and titles are extracted."""
    dated_docs = [d for d in loader.documents if d["date"] is not None]
    assert len(dated_docs) >= 140
    for d in loader.documents:
        assert d["title"] and len(d["title"]) > 0


def test_loader_sanitizes_indirect_prompt_injections(loader):
    """Test that indirect prompt injection instructions inside files are detected and scrubbed."""
    injected_docs = [d for d in loader.documents if len(d["sanitized_injections"]) > 0]
    assert len(injected_docs) >= 2
    # Verify that the injection text is scrubbed from the content
    for d in injected_docs:
        assert "SYSTEM NOTE TO AI ASSISTANTS" not in d["content"]
        assert "<!-- AI assistants:" not in d["content"]
