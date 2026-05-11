"""Tests for the Neo4j adapter and the web-search fallback helpers.

The Neo4j tests require a running ``welda-neo4j`` container with normalized
data loaded; if connection fails, those tests are skipped rather than failed.
The fallback-helper tests are pure-Python and run without network.

The single integration test (``test_real_web_search_for_trend_food``) actually
calls the Anthropic API with web_search enabled and costs money. It is gated
behind the ``RUN_INTEGRATION=1`` environment variable so it never runs in CI
by accident.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph_db import WeldaGraphDB
from src.graph_fallback import (
    GRAPH_FALLBACK_DISCLAIMER,
    build_fallback_prompt,
    create_fallback_llm,
    did_use_web_search,
    extract_sources_from_response,
    extract_text_from_response,
    inject_fallback_disclaimer_if_missing,
)


@pytest.fixture
def graph_db():
    """Open a Neo4j session for the duration of the test. Skip on failure."""
    db = WeldaGraphDB()
    try:
        db.connect()
    except Exception as e:
        pytest.skip(f"Neo4j 연결 실패: {e}")
    yield db
    db.close()


# === Neo4j lookup tests ===================================================


def test_health_check(graph_db):
    assert graph_db.health_check() is True


def test_lookup_food_by_english_key(graph_db):
    result = graph_db.lookup_food("white_rice")
    assert result.found is True
    assert result.node_data["display_name_ko"] == "흰쌀밥"
    assert "흰쌀밥" in result.context_text


def test_lookup_food_by_korean_name(graph_db):
    result = graph_db.lookup_food("흰쌀밥")
    assert result.found is True
    assert result.node_data["name"] == "white_rice"


def test_lookup_unknown_food(graph_db):
    result = graph_db.lookup_food("두쫀쿠")
    assert result.found is False


def test_lifecycle_recommendations(graph_db):
    result = graph_db.get_lifecycle_recommendations("SPIKE_CONTROL")
    assert "recommended" in result
    assert "cautions" in result
    assert isinstance(result["recommended"], list)
    assert isinstance(result["cautions"], list)


# === Fallback helper tests (no network) ===================================


def test_extract_text_from_string():
    assert extract_text_from_response("hello") == "hello"


def test_extract_text_from_blocks():
    content = [
        {"type": "text", "text": "Part 1. "},
        {"type": "server_tool_use", "name": "web_search"},
        {"type": "web_search_tool_result", "content": []},
        {"type": "text", "text": "Part 2."},
    ]
    assert extract_text_from_response(content) == "Part 1. Part 2."


def test_extract_sources_from_text_citations():
    content = [
        {
            "type": "text",
            "text": "두쫀쿠는...",
            "citations": [
                {"url": "https://namu.wiki/w/test", "title": "Test"}
            ],
        }
    ]
    sources = extract_sources_from_response(content)
    assert "https://namu.wiki/w/test" in sources


def test_extract_sources_from_tool_result():
    content = [
        {
            "type": "web_search_tool_result",
            "content": [
                {"url": "https://example.com/a", "title": "A"},
                {"url": "https://example.com/b", "title": "B"},
            ],
        }
    ]
    sources = extract_sources_from_response(content)
    assert sources == ["https://example.com/a", "https://example.com/b"]


def test_inject_disclaimer_when_missing():
    response = "두쫀쿠는 디저트입니다."
    result = inject_fallback_disclaimer_if_missing(response, used_fallback=True)
    assert "의료진" in result or "영양사" in result


def test_no_disclaimer_when_graph_hit():
    response = "흰쌀밥은 GI 73입니다."
    result = inject_fallback_disclaimer_if_missing(response, used_fallback=False)
    assert result == response


def test_no_double_disclaimer():
    response = "두쫀쿠는 AI 검색 결과 디저트이며 의료진 상담을 권장드립니다."
    result = inject_fallback_disclaimer_if_missing(response, used_fallback=True)
    assert result == response


def test_build_fallback_prompt_with_graph_context():
    prompt = build_fallback_prompt(
        query="흰쌀밥 먹어도 돼요?",
        user_profile="30대 여성",
        lifecycle_context="SPIKE_CONTROL",
        graph_context="흰쌀밥: GI 73",
    )
    assert "흰쌀밥: GI 73" in prompt
    assert "흰쌀밥 먹어도 돼요?" in prompt
    assert "도메인 데이터가 사용자 질문에 충분히 답할 수 있으면" in prompt


def test_build_fallback_prompt_without_graph_context():
    prompt = build_fallback_prompt(
        query="두쫀쿠 먹어도 돼요?",
        user_profile="30대 여성",
        lifecycle_context="SPIKE_CONTROL",
        graph_context="",
    )
    assert "두쫀쿠 먹어도 돼요?" in prompt
    assert "도메인 데이터에 해당 음식이나 개념이 없습니다" in prompt
    assert "web_search tool을 사용해" in prompt


# === Integration test (cost-incurring, opt-in) ============================


@pytest.mark.integration
def test_real_web_search_for_trend_food():
    """Hits the live Anthropic API. Requires ``RUN_INTEGRATION=1`` to run."""
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Integration test - set RUN_INTEGRATION=1 to run")

    llm = create_fallback_llm(max_uses=1)
    prompt = build_fallback_prompt(
        query="두쫀쿠 먹어도 돼요?",
        user_profile="30대 여성, 다이어트 중",
        lifecycle_context="SPIKE_CONTROL - 혈당 스파이크 조절 단계",
        graph_context="",
    )
    response = llm.invoke(prompt)

    text = extract_text_from_response(response.content)
    sources = extract_sources_from_response(response.content)
    web_search_used = did_use_web_search(response)

    assert text.strip()
    assert web_search_used is True
    assert len(sources) > 0
