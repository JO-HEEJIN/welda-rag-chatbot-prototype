"""Smoke test: vector store loads and the full chain produces a non-empty answer."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag_chain import build_rag_chain, load_vector_store


@pytest.mark.skipif(
    not (PROJECT_ROOT / "chroma_db").exists(),
    reason="chroma_db missing; run scripts/ingest.py first",
)
def test_basic_query_returns_non_empty_answer() -> None:
    vectorstore = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    components = build_rag_chain(vectorstore)

    result = components.full.invoke(
        {"question": "혈당이 무엇인가요?", "chat_history": []}
    )

    assert isinstance(result, dict)
    assert "answer" in result
    assert isinstance(result["answer"], str)
    assert result["answer"].strip(), "expected non-empty answer from the RAG chain"
    assert "sources" in result
    assert isinstance(result["sources"], list)
    assert all(isinstance(s, str) for s in result["sources"])
