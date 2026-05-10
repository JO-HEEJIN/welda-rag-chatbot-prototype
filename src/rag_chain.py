"""Build the LCEL RAG chain that powers the Welda glucose coaching chatbot.

Tracing:
    LangSmith tracing is enabled automatically when LANGSMITH_TRACING=true is
    set in .env. All LCEL chain invocations are traced step-by-step at
    https://smith.langchain.com under the project given by LANGSMITH_PROJECT.

Chain split:
    The pipeline is exposed as ``RAGChainComponents`` with three runnables:
    ``retrieval`` (single retriever call → state dict), ``generation`` (state
    dict → streamed answer), and ``full`` (both, returning {"answer", "sources"}).
    Splitting the chain lets ``stream_with_sources`` invoke retrieval once and
    only stream tokens from the generation step, eliminating a duplicate
    embedding/vector lookup that the original implementation incurred.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from operator import itemgetter

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda, RunnablePassthrough
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


LIFECYCLE_PROMPT_TEMPLATE = """당신은 웰다의 혈당 관리 코치입니다.

사용자 프로필:
{user_context}

현재 라이프사이클 단계: {lifecycle_stage_description}
이 단계의 중점 영역:
{focus_areas}

코칭 톤 가이드라인: {tone_guideline}

이 단계에서 다루지 말아야 할 주제:
{prohibited_topics}

이전 대화:
{chat_history}

관련 정보:
{context}

사용자 질문: {question}

답변 시 주의사항:
- 사용자가 현재 위 라이프사이클 단계에 있음을 의식하고 그 단계에 맞는 답변을 하세요
- prohibited_topics 에 해당하는 내용은 다루거나 권유하지 마세요
- focus_areas 에 더 비중을 두고 답변하세요
- tone_guideline 에 명시된 톤을 유지하세요
- 사용자 프로필의 의학적 조건과 식이제한을 반드시 고려하세요
- 이전 대화에서 언급된 내용을 활용하되, 새로운 질문에 집중하세요
- 의학적 자문이 필요한 사안은 반드시 의료진 상담을 권유하세요
- 컨텍스트에 없는 사실을 추측하지 마세요
- 이모지를 사용하지 마세요
- 답변은 합쇼체(공식적인 한국어 종결어미: -습니다/-십니다)로 통일하세요. 해요체(-요/-아요/-에요)는 사용하지 마세요"""


MEDICAL_DISCLAIMER_PROMPT_TEMPLATE = """당신은 웰다의 혈당 관리 코치입니다. 사용자가 의학적 자문에 가까운 질문을 했습니다. 일반 정보만 제공하고 반드시 의료진 상담을 권유하세요.

사용자 프로필:
{user_context}

이전 대화:
{chat_history}

관련 정보:
{context}

사용자 질문: {question}

답변 형식:
1. 일반적이고 교육적인 정보를 간단히 안내하세요 (진단/처방/투약 변경 권고는 절대 금지)
2. 답변 마지막에 반드시 다음 문장을 포함하세요: "이 사안은 반드시 담당 의료진과 상담해 주십시오. 약물·진단·치료 결정은 코치가 대신할 수 없습니다."
- 컨텍스트에 없는 사실을 추측하지 마세요
- 이모지를 사용하지 마세요
- 합쇼체(-습니다/-십니다)로만 답변하세요"""


@dataclass
class RAGChainComponents:
    """Three runnables exposed by ``build_rag_chain``.

    - ``retrieval``: ``{"question", "chat_history"}`` -> state dict containing
      ``retrieved_docs``, ``context``, ``sources``, ``chat_history``,
      ``user_context``, ``question``. Retriever is invoked exactly once.
    - ``generation``: state dict -> streamed answer string.
    - ``full``: end-to-end pipeline returning ``{"answer": str, "sources": list[str]}``.
    """

    retrieval: Runnable
    generation: Runnable
    full: Runnable


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


def extract_sources(docs: list[Document]) -> list[str]:
    """Sorted unique source filenames from a retriever result."""
    return sorted({d.metadata.get("source_file", "unknown") for d in docs})


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
) -> RAGChainComponents:
    """Build the retrieval, generation, and full RAG chains as LCEL Runnables.

    The chain is split so that the embedding/vector lookup happens exactly once
    per user question while the LLM response can still be streamed token by
    token. ``user_profile`` is baked into the prompt at construction time.
    """
    user_context = (
        user_profile.to_prompt_context() if user_profile is not None else "프로필 정보 없음"
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": TOP_K})
    prompt = ChatPromptTemplate.from_template(PROMPT_TEMPLATE)
    llm = ChatAnthropic(model=LLM_MODEL, temperature=0.3)

    retrieval = RunnablePassthrough.assign(
        retrieved_docs=itemgetter("question") | retriever,
    ) | RunnablePassthrough.assign(
        context=itemgetter("retrieved_docs") | RunnableLambda(format_docs),
        sources=itemgetter("retrieved_docs") | RunnableLambda(extract_sources),
        chat_history=itemgetter("chat_history") | RunnableLambda(format_chat_history),
        user_context=RunnableLambda(lambda _: user_context),
    )

    generation = prompt | llm | StrOutputParser()

    full = retrieval | {
        "answer": generation,
        "sources": itemgetter("sources"),
    }

    return RAGChainComponents(retrieval=retrieval, generation=generation, full=full)


def build_lifecycle_generation() -> Runnable:
    """Pure ``prompt | llm | parser`` for lifecycle-aware coaching responses.

    The node layer is responsible for preparing every prompt variable
    (``user_context``, formatted ``chat_history``, ``context``, ``question``,
    plus the four lifecycle fields). Keeping this runnable variable-agnostic
    makes it trivial to invoke from a LangGraph node.
    """
    prompt = ChatPromptTemplate.from_template(LIFECYCLE_PROMPT_TEMPLATE)
    llm = ChatAnthropic(model=LLM_MODEL, temperature=0.3)
    return prompt | llm | StrOutputParser()


def build_medical_disclaimer_generation() -> Runnable:
    """Generation runnable that prepends an explicit medical-referral disclaimer."""
    prompt = ChatPromptTemplate.from_template(MEDICAL_DISCLAIMER_PROMPT_TEMPLATE)
    llm = ChatAnthropic(model=LLM_MODEL, temperature=0.3)
    return prompt | llm | StrOutputParser()


def stream_with_sources(
    components: RAGChainComponents,
    question: str,
    chat_history: list[BaseMessage] | str | None,
) -> Iterator[str | tuple[str, list[str]]]:
    """Single retrieval, then token streaming with a trailing sources tuple.

    ``retrieval`` runs once via ``.invoke()`` to materialize the prompt-ready
    state (retrieved docs, formatted context, sources). ``generation`` then
    streams Claude's reply token by token off that state. This keeps the
    embedding/vector lookup to a single call per user question while still
    delivering progressive output for CLI/UI consumers.
    """
    state = components.retrieval.invoke(
        {"question": question, "chat_history": chat_history}
    )
    sources = state["sources"]

    for chunk in components.generation.stream(state):
        yield chunk

    yield ("__sources__", sources)
