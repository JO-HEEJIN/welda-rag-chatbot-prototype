"""Block 7 Part 3 GraphRAG integration tests.

Unit tests cover ``food_extraction_node`` and ``graph_lookup_node`` directly
against the running Neo4j container. If the container isn't reachable the
tests skip rather than fail.

Two integration tests exercise the full LangGraph state machine end to end
with real Anthropic API calls (web_search included). They are gated by the
``RUN_INTEGRATION=1`` environment variable since each invocation costs money.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_state import AgentState
from src.graph_db import WeldaGraphDB
from src.nodes import food_extraction_node, graph_lookup_node


def _minimum_state(question: str, intent: str = "diet_advice") -> AgentState:
    """Build a fully-populated AgentState dict for node unit tests."""
    return {
        "messages": [],
        "user_question": question,
        "user_profile_dict": {},
        "lifecycle_stage": "spike_control",
        "intent": intent,
        "retrieved_context": "",
        "sources": [],
        "final_answer": "",
        "food_query": "",
        "graph_context": "",
        "graph_found": False,
        "graph_sources": [],
        "used_web_search": False,
    }


@pytest.fixture(scope="module", autouse=True)
def _require_neo4j():
    """Skip every test in this module if the Neo4j container isn't reachable."""
    db = WeldaGraphDB()
    try:
        db.connect()
        db.close()
    except Exception as e:
        pytest.skip(f"Neo4j 연결 실패: {e}")


# === food_extraction_node ===


def test_food_extraction_finds_known_food():
    result = food_extraction_node(_minimum_state("흰쌀밥 먹어도 돼요?"))
    assert result["food_query"] == "흰쌀밥"


def test_food_extraction_picks_longest_match():
    """잡곡밥과 밥 둘 다 등록돼 있어도 더 긴 잡곡밥이 먼저 매칭돼야 함."""
    result = food_extraction_node(_minimum_state("잡곡밥 한 공기 먹어도 되나요?"))
    assert result["food_query"] == "잡곡밥"


def test_food_extraction_returns_empty_for_unknown():
    result = food_extraction_node(_minimum_state("두쫀쿠 먹어도 돼요?"))
    assert result["food_query"] == ""


def test_food_extraction_skipped_for_emergency():
    result = food_extraction_node(
        _minimum_state("흰쌀밥 먹다가 어지러워요", intent="emergency")
    )
    assert result["food_query"] == ""


def test_food_extraction_skipped_for_medical_advice():
    result = food_extraction_node(
        _minimum_state("흰쌀밥 먹어도 당뇨약 용량 줄여도 돼요?", intent="medical_advice")
    )
    assert result["food_query"] == ""


# === graph_lookup_node ===


def test_graph_lookup_hit_for_known_food():
    state = _minimum_state("흰쌀밥 먹어도 돼요?")
    state["food_query"] = "흰쌀밥"
    result = graph_lookup_node(state)
    assert result["graph_found"] is True
    assert "흰쌀밥" in result["graph_context"]
    assert "graph:food:white_rice" in result["graph_sources"]


def test_graph_lookup_empty_query():
    state = _minimum_state("아무 말이나")
    state["food_query"] = ""
    result = graph_lookup_node(state)
    assert result["graph_found"] is False
    assert result["graph_context"] == ""
    assert result["graph_sources"] == []


# === Integration: end-to-end via the compiled LangGraph ===


@pytest.mark.integration
def test_graphrag_end_to_end_known_food():
    """흰쌀밥 → graph hit, web_search 호출 없음."""
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vs = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vs)

    initial: AgentState = _minimum_state("흰쌀밥 먹어도 돼요?")
    result = graph.invoke(initial)

    assert result["graph_found"] is True
    assert result["used_web_search"] is False
    assert "흰쌀밥" in result["final_answer"]
    assert any(s.startswith("graph:food:") for s in result["sources"])


@pytest.mark.integration
def test_graphrag_end_to_end_unknown_food():
    """두쫀쿠 → graph miss → web_search fallback + citation 출처."""
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vs = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vs)

    initial: AgentState = _minimum_state("두쫀쿠 먹어도 돼요?")
    result = graph.invoke(initial)

    assert result["graph_found"] is False
    assert result["used_web_search"] is True
    answer = result["final_answer"]
    assert "두쫀쿠" in answer or "두바이" in answer
    assert "의료진" in answer or "영양사" in answer
    assert any(s.startswith("http") for s in result["sources"])
