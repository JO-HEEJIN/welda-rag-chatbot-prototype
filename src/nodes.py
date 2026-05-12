"""LangGraph node functions for the Welda lifecycle state machine.

Each node receives the shared ``AgentState`` and returns a partial dict of
fields to update. Heavy lifting (retrieval, generation) is delegated to the
existing LCEL components; nodes only orchestrate which component runs and
shape the prompt input.
"""

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agent_state import AgentState
from src.graph_db import WeldaGraphDB
from src.graph_fallback import (
    build_fallback_prompt,
    create_fallback_llm,
    did_use_web_search,
    extract_sources_from_response,
    extract_text_from_response,
    inject_fallback_disclaimer_if_missing,
)
from src.lifecycle import LIFECYCLE_METADATA, LifecycleStage, get_stage_metadata
from src.rag_chain import RAGChainComponents, format_chat_history
from src.user_profile import UserProfile


class ConstraintExtraction(BaseModel):
    """Structured output for the constraint extractor.

    Empty ``constraints`` list means the user's last utterance contained no
    standing style / forbidden-term rule (just a question, an answer, or a
    one-off formatting request).
    """

    constraints: list[str] = Field(default_factory=list)


CONSTRAINT_EXTRACTION_PROMPT = """사용자의 마지막 발화를 분석해 앞으로 챗봇 응답에 영구적으로 적용할 스타일/금지 규칙을 추출하세요.

추출 기준:
- 영구적·지속적 지시만 추출하세요. 예: "앞으로 GI 같은 용어 쓰지마", "쉬운 말로 답해", "앞으로 짧게 답해", "반말로 답해줘"
- 일회성 요청은 무시하세요. 예: "이번엔 표로 정리해줘", "지금 답변 더 길게 해줘"
- 정보 공유는 무시하세요. 예: "의사가 GI 라는 말 쓰지 말라고 했대"
- 모호하거나 추측이 필요한 경우 추출하지 마세요. 예: "이거 너무 어려워" (선호도 암시는 있지만 명시적 지시는 아님)
- 단순 질문이나 답변이면 빈 list 를 반환하세요.

추출한 규칙은 명령형 한국어 한 줄로 짧게 표현하세요. 예: "GI 같은 전문 용어 사용 금지", "쉬운 말로 답변하기".

사용자 발화:
{utterance}

위 발화에서 추출할 영구적 규칙을 list 로 반환하세요. 규칙이 없으면 빈 list 를 반환하세요."""


_constraint_extractor: ChatAnthropic | None = None


def _get_constraint_extractor():
    """Lazy-init the Haiku extractor. Reused across invocations for warmth."""
    global _constraint_extractor
    if _constraint_extractor is None:
        _constraint_extractor = ChatAnthropic(
            model="claude-haiku-4-5",
            temperature=0.0,
            max_tokens=256,
        ).with_structured_output(ConstraintExtraction)
    return _constraint_extractor

EMERGENCY_KEYWORDS = (
    "의식 잃을",
    "의식이 없",
    "응급",
    "자살",
    "심한 어지러움",
    "기절",
    "쓰러질",
    "쓰러졌",
    "구급차",
    "119",
)

MEDICAL_KEYWORDS = (
    "약 먹어도",
    "약 끊어도",
    "복용해도",
    "복용 중단",
    "처방",
    "진단",
    "투약",
    "용량",
    "약물",
    "당뇨약",
    "인슐린 주사",
)

DIET_KEYWORDS = (
    "뭐 먹",
    "추천",
    "식단",
    "메뉴",
    "먹어도 돼",
    "먹어도 되",
    "음식",
    "간식",
    "레시피",
)


def _extract_history(state: AgentState) -> list[BaseMessage]:
    return list(state.get("messages") or [])


def _format_focus_list(items: list[str]) -> str:
    if not items:
        return "(없음)"
    return "\n".join(f"- {item}" for item in items)


def classify_intent_node(state: AgentState) -> dict:
    """Rule-based intent classifier: emergency > medical > diet > general."""
    question = state["user_question"]

    if any(kw in question for kw in EMERGENCY_KEYWORDS):
        return {"intent": "emergency"}
    if any(kw in question for kw in MEDICAL_KEYWORDS):
        return {"intent": "medical_advice"}
    if any(kw in question for kw in DIET_KEYWORDS):
        return {"intent": "diet_advice"}
    return {"intent": "general"}


def extract_user_constraints_node(state: AgentState) -> dict:
    """Extract standing style / forbidden-term rules from the latest utterance.

    Sent to Haiku 4.5 with a structured-output schema so the response is always
    a typed list[str] (empty when no rule was stated). The list is appended to
    ``state["user_constraints"]`` via the AgentState ``add`` reducer, so all
    later LLM prompts see the accumulated rule set at the top of their
    instructions. Network failures degrade gracefully to no-op (empty list).
    """
    utterance = state["user_question"]
    try:
        extractor = _get_constraint_extractor()
        result: ConstraintExtraction = extractor.invoke(
            CONSTRAINT_EXTRACTION_PROMPT.format(utterance=utterance)
        )
        new_rules = [c.strip() for c in (result.constraints or []) if c and c.strip()]
    except Exception as exc:
        print(f"[extract_user_constraints] 추출 실패, 건너뜀: {exc}")
        return {"user_constraints": []}

    return {"user_constraints": new_rules}


def rag_node(state: AgentState, components: RAGChainComponents) -> dict:
    """Run the existing retrieval chain once and stash context+sources in state."""
    history = _extract_history(state)
    retrieval_state = components.retrieval.invoke(
        {"question": state["user_question"], "chat_history": history}
    )
    return {
        "retrieved_context": retrieval_state["context"],
        "sources": retrieval_state["sources"],
    }


def generate_response_node(
    state: AgentState,
    lifecycle_gen,
    user_profile: UserProfile | None,
) -> dict:
    """Render the lifecycle-aware coach prompt and call the LLM."""
    stage = LifecycleStage(state["lifecycle_stage"])
    meta = get_stage_metadata(stage)

    user_context = (
        user_profile.to_prompt_context() if user_profile is not None else "프로필 정보 없음"
    )
    chat_history_text = format_chat_history(_extract_history(state))

    prompt_input = {
        "user_context": user_context,
        "chat_history": chat_history_text,
        "context": state.get("retrieved_context", "(검색된 컨텍스트 없음)"),
        "question": state["user_question"],
        "lifecycle_stage_description": meta.description,
        "focus_areas": _format_focus_list(meta.focus_areas),
        "tone_guideline": meta.tone_guideline,
        "prohibited_topics": _format_focus_list(meta.prohibited_topics),
    }

    answer = lifecycle_gen.invoke(prompt_input)
    return {
        "final_answer": answer,
        "messages": [
            HumanMessage(content=state["user_question"]),
            AIMessage(content=answer),
        ],
    }


def emergency_response_node(state: AgentState) -> dict:
    """Bypass RAG and respond with an immediate medical-referral message."""
    answer = (
        "응급 증상이 의심됩니다. 즉시 119에 신고하시거나 가까운 응급실로 이동해 주십시오.\n\n"
        "혈당 관리 코치는 응급 상황에서 의료진을 대체할 수 없습니다. "
        "의식 저하·심한 어지러움·실신 위험이 있다면 지금 바로 의료진의 도움을 받으십시오. "
        "주변에 보호자가 있다면 함께 있도록 요청하시고, 안전한 곳에 앉거나 누워 계십시오. "
        "저혈당이 의심되고 의식이 있다면 단순당(주스, 사탕 등)을 섭취하시고 즉시 의료진과 연락해 주십시오."
    )
    return {
        "final_answer": answer,
        "sources": [],
        "messages": [
            HumanMessage(content=state["user_question"]),
            AIMessage(content=answer),
        ],
    }


def medical_disclaimer_node(
    state: AgentState,
    components: RAGChainComponents,
    medical_gen,
    user_profile: UserProfile | None,
) -> dict:
    """Provide general info from RAG, then append a mandatory referral line."""
    history = _extract_history(state)
    retrieval_state = components.retrieval.invoke(
        {"question": state["user_question"], "chat_history": history}
    )

    user_context = (
        user_profile.to_prompt_context() if user_profile is not None else "프로필 정보 없음"
    )
    constraints = state.get("user_constraints") or []
    constraints_block = (
        "\n".join(f"- {c}" for c in constraints) if constraints else "(없음)"
    )
    prompt_input = {
        "user_context": user_context,
        "chat_history": format_chat_history(history),
        "context": retrieval_state["context"],
        "question": state["user_question"],
        "user_constraints": constraints_block,
    }

    answer = medical_gen.invoke(prompt_input)
    return {
        "final_answer": answer,
        "retrieved_context": retrieval_state["context"],
        "sources": retrieval_state["sources"],
        "messages": [
            HumanMessage(content=state["user_question"]),
            AIMessage(content=answer),
        ],
    }


def food_extraction_node(state: AgentState) -> dict:
    """Find the first known food name (display_name_ko) that appears in the query.

    Only runs for diet_advice / general intents — emergency and medical_advice
    skip food extraction since their routes don't need graph context. Match is
    substring-based against the longest-first list of food names so "잡곡밥"
    beats the shorter "밥" when both could match. Neo4j failures degrade
    gracefully: an empty ``food_query`` triggers the web-search fallback path.
    """
    if state.get("intent") in ("emergency", "medical_advice"):
        return {"food_query": ""}

    query = state["user_question"]
    try:
        with WeldaGraphDB() as db:
            for name in db.get_all_food_korean_names():
                if name in query:
                    return {"food_query": name}
    except Exception as exc:
        print(f"[food_extraction] Neo4j 연결 실패, 건너뜀: {exc}")
        return {"food_query": ""}

    return {"food_query": ""}


def graph_lookup_node(state: AgentState) -> dict:
    """Resolve the extracted food name through the Neo4j multi-hop traversal.

    Populates ``graph_context`` / ``graph_found`` / ``graph_sources`` so the
    downstream generator can decide whether the graph data is sufficient or
    the web-search fallback is needed. Empty ``food_query`` short-circuits.
    """
    food_query = state.get("food_query", "")

    if not food_query:
        return {"graph_context": "", "graph_found": False, "graph_sources": []}

    try:
        with WeldaGraphDB() as db:
            result = db.lookup_food(food_query)
            if result.found:
                return {
                    "graph_context": result.context_text,
                    "graph_found": True,
                    "graph_sources": result.sources,
                }
    except Exception as exc:
        print(f"[graph_lookup] Neo4j lookup 실패: {exc}")

    return {"graph_context": "", "graph_found": False, "graph_sources": []}


def generate_or_fallback_node(
    state: AgentState,
    user_profile: UserProfile | None,
) -> dict:
    """Generate the final answer using graph + RAG context, falling back to web_search.

    The Anthropic ``web_search`` tool is always attached to the LLM, but the
    model only invokes it when the supplied context (graph + RAG) is
    insufficient. This lets the model itself decide hit-vs-miss instead of a
    fragile client-side heuristic. Sources from graph, RAG, and any web search
    citations are merged (dedup-preserving order).
    """
    stage_value = state["lifecycle_stage"]
    stage_enum = LifecycleStage(stage_value)
    meta = LIFECYCLE_METADATA[stage_enum]
    lifecycle_context = (
        f"{stage_value} — {meta.description}. "
        f"중점 영역: {', '.join(meta.focus_areas) or '(없음)'}. "
        f"코칭 톤: {meta.tone_guideline}"
    )

    user_profile_str = (
        user_profile.to_prompt_context()
        if user_profile is not None
        else "프로필 정보 없음"
    )

    parts: list[str] = []
    graph_ctx = state.get("graph_context", "")
    rag_ctx = state.get("retrieved_context", "")
    if graph_ctx:
        parts.append(f"[도메인 그래프 데이터]\n{graph_ctx}")
    if rag_ctx:
        parts.append(f"[일반 도메인 문서]\n{rag_ctx}")
    combined_context = "\n\n".join(parts)

    history = _extract_history(state)
    chat_history_text = format_chat_history(history)
    user_constraints = list(state.get("user_constraints") or [])

    llm = create_fallback_llm(max_uses=3)
    prompt = build_fallback_prompt(
        query=state["user_question"],
        user_profile=user_profile_str,
        lifecycle_context=lifecycle_context,
        graph_context=combined_context,
        chat_history=chat_history_text,
        user_constraints=user_constraints,
    )
    response = llm.invoke(prompt)

    text = extract_text_from_response(response.content)
    web_sources = extract_sources_from_response(response.content)
    web_used = did_use_web_search(response)
    final_answer = inject_fallback_disclaimer_if_missing(text, used_fallback=web_used)

    merged: list[str] = []
    seen: set[str] = set()
    for src in list(state.get("sources") or []) + list(state.get("graph_sources") or []) + web_sources:
        if src and src not in seen:
            seen.add(src)
            merged.append(src)

    return {
        "final_answer": final_answer,
        "sources": merged,
        "used_web_search": web_used,
        "messages": [
            HumanMessage(content=state["user_question"]),
            AIMessage(content=final_answer),
        ],
    }
