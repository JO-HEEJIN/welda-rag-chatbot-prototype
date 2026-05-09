"""Load markdown files from the knowledge directory and split them into chunks."""

from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_and_split_documents(knowledge_dir: str = "welda_knowledge") -> list[Document]:
    """Read every .md file in ``knowledge_dir`` and return chunked LangChain Documents.

    Each chunk preserves the originating file name in ``metadata["source_file"]``
    so the chat layer can cite which document was retrieved.
    """
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    chunks: list[Document] = []
    for md_file in sorted(Path(knowledge_dir).glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for piece in splitter.split_text(text):
            chunks.append(
                Document(
                    page_content=piece,
                    metadata={"source_file": md_file.name},
                )
            )
    return chunks
