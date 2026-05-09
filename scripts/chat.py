"""CLI chat interface for the Welda RAG chatbot."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag_chain import build_rag_chain, load_vector_store


def main() -> None:
    persist_dir = PROJECT_ROOT / "chroma_db"
    if not persist_dir.exists():
        print(f"[chat] No index found at {persist_dir}. Run scripts/ingest.py first.")
        return

    vectorstore = load_vector_store(str(persist_dir))
    chain = build_rag_chain(vectorstore)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    print("[chat] Welda glucose coach. Type 'exit' or 'quit' to leave.")
    while True:
        try:
            question = input(">>> ").strip()
        except EOFError:
            break
        if not question:
            continue
        if question.lower() in {"exit", "quit"}:
            break

        docs = retriever.invoke(question)
        sources = sorted({d.metadata.get("source_file", "unknown") for d in docs})

        answer = chain.invoke({"question": question, "user_profile": {}})
        print(f"\n{answer}\n")
        print(f"참고: {', '.join(sources)}\n")


if __name__ == "__main__":
    main()
