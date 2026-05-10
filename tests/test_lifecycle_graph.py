"""Structural and behavioral tests for the lifecycle LangGraph state machine."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.lifecycle import (
    LIFECYCLE_METADATA,
    LifecycleStage,
    get_stage_metadata,
)
from src.nodes import classify_intent_node


# ---------------------------- lifecycle metadata ----------------------------


def test_all_five_lifecycle_stages_defined() -> None:
    expected = {
        LifecycleStage.UNDERSTANDING,
        LifecycleStage.SPIKE_CONTROL,
        LifecycleStage.HUNGER_CONTROL,
        LifecycleStage.FAT_BURN,
        LifecycleStage.MAINTENANCE,
    }
    assert set(LIFECYCLE_METADATA.keys()) == expected


def test_each_stage_has_complete_metadata() -> None:
    for stage in LifecycleStage:
        meta = get_stage_metadata(stage)
        assert meta.description, f"{stage} description missing"
        assert meta.focus_areas, f"{stage} focus_areas missing"
        assert meta.tone_guideline, f"{stage} tone_guideline missing"
        assert meta.prohibited_topics, f"{stage} prohibited_topics missing"


# ---------------------------- intent classifier ----------------------------


def test_intent_classifier_detects_emergency_keywords() -> None:
    state = {"user_question": "어지러워서 의식 잃을 것 같아요"}
    assert classify_intent_node(state) == {"intent": "emergency"}


def test_intent_classifier_detects_medical_keywords() -> None:
    state = {"user_question": "당뇨약 먹어도 돼요?"}
    assert classify_intent_node(state) == {"intent": "medical_advice"}


def test_intent_classifier_detects_diet_keywords() -> None:
    state = {"user_question": "점심에 뭐 먹으면 좋을까요?"}
    assert classify_intent_node(state) == {"intent": "diet_advice"}


def test_intent_classifier_falls_back_to_general() -> None:
    state = {"user_question": "혈당 스파이크가 무엇인가요?"}
    assert classify_intent_node(state) == {"intent": "general"}


def test_emergency_takes_priority_over_medical() -> None:
    state = {"user_question": "처방받은 약을 먹었는데 의식 잃을 것 같아요"}
    assert classify_intent_node(state) == {"intent": "emergency"}


# ---------------------------- graph routing ----------------------------


@pytest.mark.skipif(
    not (PROJECT_ROOT / "chroma_db").exists(),
    reason="chroma_db missing; run scripts/ingest.py first",
)
def test_emergency_intent_skips_rag() -> None:
    """Emergency path must not touch retrieval and must produce a referral message."""
    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vectorstore = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vectorstore, user_profile=None)

    result = graph.invoke(
        {
            "user_question": "어지러워서 의식 잃을 것 같아요",
            "lifecycle_stage": LifecycleStage.UNDERSTANDING.value,
            "messages": [],
        }
    )

    assert result["intent"] == "emergency"
    # Emergency answer is a fixed string, not RAG-generated
    assert "119" in result["final_answer"]
    assert "응급" in result["final_answer"] or "의료진" in result["final_answer"]
    # No retrieval ran
    assert result.get("sources") == [] or result.get("sources") is None
    assert result.get("retrieved_context") in (None, "")


@pytest.mark.skipif(
    not (PROJECT_ROOT / "chroma_db").exists(),
    reason="chroma_db missing; run scripts/ingest.py first",
)
def test_medical_intent_includes_referral() -> None:
    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vectorstore = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vectorstore, user_profile=None)

    result = graph.invoke(
        {
            "user_question": "당뇨약 복용 중인데 용량을 줄여도 되나요?",
            "lifecycle_stage": LifecycleStage.SPIKE_CONTROL.value,
            "messages": [],
        }
    )

    assert result["intent"] == "medical_advice"
    assert "의료진" in result["final_answer"]


@pytest.mark.skipif(
    not (PROJECT_ROOT / "chroma_db").exists(),
    reason="chroma_db missing; run scripts/ingest.py first",
)
def test_general_intent_runs_through_rag_and_generate() -> None:
    from src.graph import build_lifecycle_graph
    from src.rag_chain import load_vector_store

    vectorstore = load_vector_store(str(PROJECT_ROOT / "chroma_db"))
    graph = build_lifecycle_graph(vectorstore, user_profile=None)

    result = graph.invoke(
        {
            "user_question": "혈당 스파이크가 무엇인가요?",
            "lifecycle_stage": LifecycleStage.UNDERSTANDING.value,
            "messages": [],
        }
    )

    assert result["intent"] == "general"
    assert result["final_answer"].strip()
    assert isinstance(result["sources"], list)
    assert result["retrieved_context"]
