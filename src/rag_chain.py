"""Build the LCEL RAG chain that powers the Welda glucose coaching chatbot."""

from operator import itemgetter

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

EMBEDDING_MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "welda_knowledge"
LLM_MODEL = "claude-sonnet-4-6"
TOP_K = 3

PROMPT_TEMPLATE = """당신은 웰다(Welda)의 혈당 관리 코치입니다. 사용자의 혈당 관련 질문에 대해, 아래에 제공된 컨텍스트만을 근거로 정확하고 친절하게 답변하십시오.

다음 원칙을 지켜주십시오.
1. 컨텍스트에 없는 사실은 추측하지 말고, 정보가 부족하면 "제공된 정보로는 답변하기 어렵습니다"라고 솔직하게 말하십시오.
2. 의학적 진단, 약물 조정, 개인의 임상적 의사결정이 필요한 사안이라고 판단되면 답변 끝에 의료진 상담을 권유하는 한 문장을 덧붙이십시오.
3. 합쇼체로 답변하십시오.
4. 이모지를 사용하지 마십시오. 강조가 필요한 경우 마크다운 굵게(**텍스트**)나 리스트만 사용하십시오.

[사용자 프로필]
{user_profile}

[컨텍스트]
{context}

[사용자 질문]
{question}

답변:"""


def load_vector_store(persist_dir: str = "./chroma_db") -> Chroma:
    """Open the existing Chroma collection at ``persist_dir`` for retrieval."""
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    return Chroma(
        persist_directory=persist_dir,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
    )


def format_docs(docs: list[Document]) -> str:
    """Render retrieved chunks as ``[source: filename]\\n<content>`` blocks."""
    return "\n\n".join(
        f"[source: {d.metadata.get('source_file', 'unknown')}]\n{d.page_content}"
        for d in docs
    )


def build_rag_chain(vectorstore: Chroma) -> Runnable:
    """Compose the LCEL pipeline: retrieval -> prompt -> Claude -> string output.

    The chain expects ``{"question": str, "user_profile": dict}`` as input.
    ``user_profile`` is a placeholder for Block 4 personalization and may be ``{}``.
    """
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    prompt = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    llm = ChatAnthropic(model=LLM_MODEL, temperature=0.3)

    return (
        {
            "context": itemgetter("question") | retriever | format_docs,
            "question": itemgetter("question"),
            "user_profile": itemgetter("user_profile"),
        }
        | prompt
        | llm
        | StrOutputParser()
    )
