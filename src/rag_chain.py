"""Build the LCEL RAG chain that powers the Welda glucose coaching chatbot.

Tracing:
    LangSmith tracing is enabled automatically when LANGSMITH_TRACING=true is
    set in .env. All LCEL chain invocations are traced step-by-step at
    https://smith.langchain.com under the project given by LANGSMITH_PROJECT.
"""

from collections.abc import Iterator
from operator import itemgetter

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_huggingface import HuggingFaceEmbeddings

from src.user_profile import UserProfile

load_dotenv()

EMBEDDING_MODEL = "BAAI/bge-m3"
COLLECTION_NAME = "welda_knowledge"
LLM_MODEL = "claude-sonnet-4-6"
TOP_K = 3

PROMPT_TEMPLATE = """당신은 웰다의 혈당 관리 코치입니다. 사용자 프로필과 이전 대화를 고려해 답변하세요.

사용자 프로필:
{user_context}

이전 대화:
{chat_history}

관련 정보:
{context}

사용자 질문: {question}

답변 시 주의사항:
- 사용자 프로필의 의학적 조건과 식이제한을 반드시 고려하세요
- 이전 대화에서 언급된 내용을 활용하되, 새로운 질문에 집중하세요
- 의학적 자문이 필요한 사안은 반드시 의료진 상담을 권유하세요
- 컨텍스트에 없는 사실을 추측하지 마세요
- 이모지를 사용하지 마세요
- 답변은 합쇼체(공식적인 한국어 종결어미: -습니다/-십니다)로 통일하세요. 해요체(-요/-아요/-에요)는 사용하지 마세요"""


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


def format_chat_history(history: list[BaseMessage] | str | None) -> str:
    """Convert a list of LangChain messages into a single prompt-ready string."""
    if isinstance(history, str):
        return history if history.strip() else "이전 대화 없음"
    if not history:
        return "이전 대화 없음"

    lines: list[str] = []
    for msg in history:
        if isinstance(msg, HumanMessage):
            role = "사용자"
        elif isinstance(msg, AIMessage):
            role = "코치"
        else:
            role = msg.type
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)


def build_rag_chain(
    vectorstore: Chroma,
    user_profile: UserProfile | None = None,
) -> Runnable:
    """Compose the LCEL pipeline: retrieval -> prompt -> Claude -> string output.

    The chain expects ``{"question": str, "chat_history": list[BaseMessage] | str}``
    as input. ``user_profile`` is fixed at chain construction time; pass ``None``
    to omit personalization.
    """
    user_context = (
        user_profile.to_prompt_context() if user_profile is not None else "프로필 정보 없음"
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    prompt = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    llm = ChatAnthropic(model=LLM_MODEL, temperature=0.3)

    return (
        {
            "context": itemgetter("question") | retriever | format_docs,
            "question": itemgetter("question"),
            "chat_history": itemgetter("chat_history") | RunnableLambda(format_chat_history),
            "user_context": RunnableLambda(lambda _: user_context),
        }
        | prompt
        | llm
        | StrOutputParser()
    )


def stream_with_sources(
    chain: Runnable,
    vectorstore: Chroma,
    question: str,
    chat_history: list[BaseMessage] | str | None,
) -> Iterator[str | tuple[str, list[str]]]:
    """Stream the chain's tokens, then emit a final ``("__sources__", [...])``.

    The retriever is called once up front so we can attach source filenames to
    the response without making the streaming chain itself emit metadata. The
    extra retriever call is cheap because the chain runs the same retrieval
    internally; vector lookup time is dominated by embedding the query, which
    happens twice but is well under 100 ms locally.
    """
    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    docs = retriever.invoke(question)
    sources = sorted({d.metadata.get("source_file", "unknown") for d in docs})

    for chunk in chain.stream({"question": question, "chat_history": chat_history}):
        yield chunk

    yield ("__sources__", sources)
