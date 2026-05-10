"""Run a fixed set of simulations across the lifecycle graph for verification.

This script is invoked once during Block 6 verification. It exercises:
- the same diet question across UNDERSTANDING / SPIKE_CONTROL / FAT_BURN
- an emergency-keyword question (must hit emergency node, no RAG)
- a medical-advice-keyword question (must include medical referral)

Output goes to stdout for human inspection.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.graph import build_lifecycle_graph
from src.lifecycle import LIFECYCLE_METADATA, LifecycleStage
from src.rag_chain import load_vector_store

DIVIDER = "=" * 70


def run_case(graph, label: str, question: str, stage: LifecycleStage) -> None:
    print(DIVIDER)
    print(f"[{label}]")
    print(f"단계: {stage.value} — {LIFECYCLE_METADATA[stage].description}")
    print(f"질문: {question}")
    print(DIVIDER)
    result = graph.invoke(
        {
            "user_question": question,
            "lifecycle_stage": stage.value,
            "messages": [],
        }
    )
    print(f"intent: {result.get('intent')}")
    print(f"sources: {result.get('sources')}")
    print()
    print(result["final_answer"])
    print()


def main() -> None:
    persist_dir = PROJECT_ROOT / "chroma_db"
    if not persist_dir.exists():
        print(f"chroma_db not found at {persist_dir}. Run scripts/ingest.py first.")
        sys.exit(1)

    vectorstore = load_vector_store(str(persist_dir))
    graph = build_lifecycle_graph(vectorstore, user_profile=None)

    diet_question = "흰쌀밥 먹어도 돼요?"

    run_case(graph, "Stage 1: UNDERSTANDING", diet_question, LifecycleStage.UNDERSTANDING)
    run_case(graph, "Stage 2: SPIKE_CONTROL", diet_question, LifecycleStage.SPIKE_CONTROL)
    run_case(graph, "Stage 4: FAT_BURN", diet_question, LifecycleStage.FAT_BURN)

    run_case(
        graph,
        "Emergency",
        "어지러워서 의식 잃을 것 같아요",
        LifecycleStage.UNDERSTANDING,
    )

    run_case(
        graph,
        "Medical advice",
        "당뇨약 복용 중인데 용량 줄여도 되나요?",
        LifecycleStage.SPIKE_CONTROL,
    )


if __name__ == "__main__":
    main()
