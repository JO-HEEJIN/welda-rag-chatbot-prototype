"""Smoke test: vector store loads and chain produces a non-empty response."""

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
    chain = build_rag_chain(vectorstore)

    answer = chain.invoke({"question": "혈당이 무엇인가요?", "chat_history": []})

    assert isinstance(answer, str)
    assert answer.strip(), "expected non-empty answer from the RAG chain"
