"""Build the Chroma index from welda_knowledge/. Run once before chatting."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.build_index import build_vector_store
from src.load_documents import load_and_split_documents


def main() -> None:
    knowledge_dir = PROJECT_ROOT / "welda_knowledge"
    persist_dir = PROJECT_ROOT / "chroma_db"

    print(f"[ingest] Loading and splitting documents from {knowledge_dir}")
    chunks = load_and_split_documents(str(knowledge_dir))
    print(f"[ingest] Produced {len(chunks)} chunks")

    print(f"[ingest] Building vector store at {persist_dir} (force_rebuild=True)")
    build_vector_store(chunks, persist_dir=str(persist_dir), force_rebuild=True)
    print("[ingest] Index build complete")


if __name__ == "__main__":
    main()
