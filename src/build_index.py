"""Build a Chroma vector store from chunked documents using BGE-M3 embeddings."""

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

EMBEDDING_MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "welda_knowledge"


def build_vector_store(
    documents: list[Document],
    persist_dir: str = "./chroma_db",
    force_rebuild: bool = False,
) -> Chroma:
    """Embed ``documents`` with BGE-M3 and persist them to ``persist_dir``.

    When ``force_rebuild`` is True, an existing index at ``persist_dir`` is
    deleted before the new one is created so the collection cannot accumulate
    duplicate chunks across runs.
    """
    if force_rebuild and Path(persist_dir).exists():
        shutil.rmtree(persist_dir)

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    return Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name=COLLECTION_NAME,
    )
