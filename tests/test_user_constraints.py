"""Tests for Block 8 user-constraint extraction and prompt injection.

The extractor is an LLM call (Haiku 4.5 with structured output), so genuine
behavioural checks are kept under the ``integration`` marker (run with
``RUN_INTEGRATION=1``). Pure-string checks for ``_format_user_constraints``
and ``build_fallback_prompt`` run without network.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph_fallback import _format_user_constraints, build_fallback_prompt


# === pure-string helpers (no network) ====================================


def test_format_user_constraints_empty():
    assert _format_user_constraints([]) == "(없음)"
    assert _format_user_constraints(None) == "(없음)"
    assert _format_user_constraints(["", "   "]) == "(없음)"


def test_format_user_constraints_bullets():
    text = _format_user_constraints(
        ["GI 같은 전문 용어 사용 금지", "쉬운 말로 답변하기"]
    )
    assert "- GI 같은 전문 용어 사용 금지" in text
    assert "- 쉬운 말로 답변하기" in text


def test_build_fallback_prompt_includes_constraints_block_when_empty():
    prompt = build_fallback_prompt(
        query="흰쌀밥 먹어도 돼요?",
        user_profile="30대 여성",
        lifecycle_context="SPIKE_CONTROL",
        graph_context="흰쌀밥: GI 73",
    )
    assert "[사용자가 명시한 규칙" in prompt
    assert "(없음)" in prompt
    # 강조 instruction 도 항상 따라가야 함
    assert "사용자가 명시한 규칙]을 절대 어기지 마세요" in prompt


def test_build_fallback_prompt_lists_constraints_when_present():
    prompt = build_fallback_prompt(
        query="흰쌀밥 먹어도 돼요?",
        user_profile="30대 여성",
        lifecycle_context="SPIKE_CONTROL",
        graph_context="흰쌀밥: GI 73",
        chat_history="사용자: GI 쓰지마\n코치: 알겠습니다",
        user_constraints=["GI 같은 전문 용어 사용 금지"],
    )
    assert "- GI 같은 전문 용어 사용 금지" in prompt
    # chat_history 도 함께 들어가야 함 (Block 8 회귀 방지)
    assert "사용자: GI 쓰지마" in prompt


def test_build_fallback_prompt_empty_history_renders_sentinel():
    prompt = build_fallback_prompt(
        query="Q",
        user_profile="P",
        lifecycle_context="L",
        graph_context="",
        chat_history="",
        user_constraints=None,
    )
    assert "이전 대화:\n(없음)" in prompt


# === extractor end-to-end (LLM, integration only) ========================


@pytest.mark.integration
def test_extract_explicit_forbid_term():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.agent_state import AgentState
    from src.nodes import extract_user_constraints_node

    state: AgentState = {  # type: ignore[typeddict-item]
        "user_question": "GI 같은 전문 용어 앞으로 쓰지마",
        "messages": [],
        "user_profile_dict": {},
        "lifecycle_stage": "spike_control",
        "intent": "general",
        "retrieved_context": "",
        "sources": [],
        "final_answer": "",
        "food_query": "",
        "graph_context": "",
        "graph_found": False,
        "graph_sources": [],
        "used_web_search": False,
        "user_constraints": [],
    }
    result = extract_user_constraints_node(state)
    rules = result["user_constraints"]
    assert rules, f"expected at least one extracted rule, got {rules}"
    # 추출된 규칙 중 적어도 하나가 GI 와 금지 의미를 담아야 함
    assert any("GI" in r and ("금지" in r or "쓰" in r) for r in rules), rules


@pytest.mark.integration
def test_extract_one_off_request_returns_empty():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.nodes import extract_user_constraints_node

    state = {
        "user_question": "이번 답변은 표로 정리해줘",
        "messages": [],
        "user_profile_dict": {},
        "lifecycle_stage": "spike_control",
        "intent": "general",
        "retrieved_context": "",
        "sources": [],
        "final_answer": "",
        "food_query": "",
        "graph_context": "",
        "graph_found": False,
        "graph_sources": [],
        "used_web_search": False,
        "user_constraints": [],
    }
    result = extract_user_constraints_node(state)
    assert result["user_constraints"] == [], result["user_constraints"]


@pytest.mark.integration
def test_extract_plain_question_returns_empty():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.nodes import extract_user_constraints_node

    state = {
        "user_question": "흰쌀밥 먹어도 돼요?",
        "messages": [],
        "user_profile_dict": {},
        "lifecycle_stage": "spike_control",
        "intent": "diet_advice",
        "retrieved_context": "",
        "sources": [],
        "final_answer": "",
        "food_query": "",
        "graph_context": "",
        "graph_found": False,
        "graph_sources": [],
        "used_web_search": False,
        "user_constraints": [],
    }
    result = extract_user_constraints_node(state)
    assert result["user_constraints"] == [], result["user_constraints"]


@pytest.mark.integration
def test_constraints_accumulate_across_turns():
    """첫 턴에서 'GI 쓰지마' 추출 후, 두 번째 일반 질문에서 응답이 GI 단어 회피."""
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vs = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vs)

    def base(question: str, prior_constraints: list[str]) -> dict:
        return {
            "messages": [],
            "user_question": question,
            "user_profile_dict": {},
            "lifecycle_stage": "spike_control",
            "intent": "",
            "retrieved_context": "",
            "sources": [],
            "final_answer": "",
            "food_query": "",
            "graph_context": "",
            "graph_found": False,
            "graph_sources": [],
            "used_web_search": False,
            "user_constraints": list(prior_constraints),
        }

    turn1 = graph.invoke(base("앞으로 GI 라는 단어 쓰지마. 알겠지?", []))
    constraints_after_turn1 = turn1.get("user_constraints") or []
    assert constraints_after_turn1, "expected a rule after the explicit forbid"

    turn2 = graph.invoke(
        base("흰쌀밥 먹어도 돼요?", constraints_after_turn1)
    )
    final = turn2["final_answer"]
    assert "GI" not in final, f"GI mention slipped through despite the rule: {final[:200]}"
