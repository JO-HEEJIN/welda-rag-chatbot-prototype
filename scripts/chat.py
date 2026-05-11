"""CLI chat interface for the Welda RAG chatbot powered by the lifecycle graph."""

import sys
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.conversation_memory import ConversationManager
from src.graph import build_lifecycle_graph
from src.lifecycle import LIFECYCLE_METADATA, LifecycleStage
from src.rag_chain import load_vector_store
from src.user_profile import UserProfile

DIET_GOAL_CHOICES = {
    "1": "weight_loss",
    "2": "blood_sugar_control",
    "3": "muscle_gain",
    "4": "maintenance",
}

INSULIN_LEVEL_CHOICES = {"1": "low", "2": "moderate", "3": "high"}

GENDER_CHOICES = {"1": "male", "2": "female", "3": "other"}

LIFECYCLE_CHOICES: dict[str, LifecycleStage] = {
    "1": LifecycleStage.UNDERSTANDING,
    "2": LifecycleStage.SPIKE_CONTROL,
    "3": LifecycleStage.HUNGER_CONTROL,
    "4": LifecycleStage.FAT_BURN,
    "5": LifecycleStage.MAINTENANCE,
}


def ask_int(prompt: str, low: int, high: int) -> int:
    while True:
        raw = input(prompt).strip()
        try:
            value = int(raw)
        except ValueError:
            print(f"  정수를 입력하세요. ({low}-{high})")
            continue
        if not (low <= value <= high):
            print(f"  {low}-{high} 범위 안의 값을 입력하세요.")
            continue
        return value


def ask_optional_float(prompt: str, low: float, high: float) -> float | None:
    while True:
        raw = input(prompt).strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            print(f"  숫자를 입력하거나 빈칸으로 두세요. ({low:g}-{high:g})")
            continue
        if not (low <= value <= high):
            print(f"  {low:g}-{high:g} 범위 안의 값을 입력하거나 빈칸으로 두세요.")
            continue
        return value


def ask_choice(prompt: str, choices: dict[str, str]) -> str:
    options_str = ", ".join(f"{k}={v}" for k, v in choices.items())
    while True:
        raw = input(f"{prompt} ({options_str}): ").strip()
        if raw in choices:
            return choices[raw]
        print(f"  {', '.join(choices.keys())} 중 하나를 입력하세요.")


def ask_string_list(prompt: str) -> list[str]:
    raw = input(prompt).strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def ask_lifecycle_stage() -> LifecycleStage:
    print("\n[라이프사이클 단계 선택]")
    for key, stage in LIFECYCLE_CHOICES.items():
        meta = LIFECYCLE_METADATA[stage]
        print(f"  {key}. {meta.description}")
    while True:
        raw = input("현재 어느 단계에 계신가요? (1-5): ").strip()
        if raw in LIFECYCLE_CHOICES:
            return LIFECYCLE_CHOICES[raw]
        print("  1-5 중 하나를 입력하세요.")


def build_profile_interactively() -> UserProfile:
    print("\n[프로필 입력] 항목별로 답해 주십시오. 빈칸으로 두면 기본값/생략 처리됩니다.\n")
    while True:
        age = ask_int("나이(1-120): ", 1, 120)
        gender = ask_choice("성별", GENDER_CHOICES)
        insulin = ask_choice("인슐린 저항성", INSULIN_LEVEL_CHOICES)
        glucose = ask_optional_float(
            "평균 공복혈당 (mg/dL, 50-300, 모르면 빈칸): ", 50, 300
        )
        diet_goal = ask_choice("다이어트 목표", DIET_GOAL_CHOICES)
        conditions = ask_string_list(
            "만성질환 (콤마로 구분, 예: diabetes_type2, hypertension. 없으면 빈칸): "
        )
        restrictions = ask_string_list(
            "식이제한 (콤마로 구분, 예: lactose_intolerant, vegetarian. 없으면 빈칸): "
        )

        try:
            return UserProfile(
                age=age,
                gender=gender,
                insulin_resistance_level=insulin,
                avg_fasting_glucose=glucose,
                diet_goal=diet_goal,
                medical_conditions=conditions,
                dietary_restrictions=restrictions,
            )
        except ValidationError as exc:
            print(f"\n프로필 검증 실패. 다시 입력해 주십시오.\n{exc}\n")


def main() -> None:
    persist_dir = PROJECT_ROOT / "chroma_db"
    if not persist_dir.exists():
        print(f"[chat] No index found at {persist_dir}. Run scripts/ingest.py first.")
        return

    print("[chat] Welda 혈당 관리 코치 CLI 데모입니다 (LangGraph 라이프사이클 모드).")
    print("[chat] 명령: exit/quit (종료), reset (메모리 초기화), history (대화 기록), profile (프로필 보기), stage (단계 보기/변경)\n")

    profile: UserProfile | None = None
    answer = input("사용자 프로필을 설정하시겠습니까? (y/n): ").strip().lower()
    if answer == "y":
        profile = build_profile_interactively()
        print(f"\n[프로필 저장됨] {profile.to_prompt_context()}\n")
    else:
        print("[프로필 없이 진행]\n")

    stage = ask_lifecycle_stage()
    print(f"\n[단계 저장됨] {LIFECYCLE_METADATA[stage].description}\n")

    vectorstore = load_vector_store(str(persist_dir))
    graph = build_lifecycle_graph(vectorstore, user_profile=profile)
    memory = ConversationManager(max_turns=10)

    print()
    print("=" * 60)
    print("준비가 완료되었습니다. 혈당 관리에 대해 질문해 주십시오.")
    print("예시: '아침에는 마라탕 먹어도 되지 않나요?'")
    print("명령: history  profile  stage  reset  exit")
    print("=" * 60)
    print("\n사용 가능한 명령어:")
    print("  exit / quit  - 대화를 종료합니다")
    print("  reset        - 대화 메모리를 초기화합니다")
    print("  history      - 지금까지의 대화 기록을 봅니다")
    print("  profile      - 현재 사용자 프로필을 확인합니다")
    print()

    while True:
        try:
            question = input("\n>>> ").strip()
        except EOFError:
            break
        if not question:
            continue

        cmd = question.lower()
        if cmd in {"exit", "quit"}:
            break
        if cmd == "reset":
            memory.clear()
            print("[메모리 초기화 완료]\n")
            continue
        if cmd == "history":
            text = memory.get_history_as_text()
            print(text if text else "[기록 없음]")
            print()
            continue
        if cmd == "profile":
            if profile is None:
                print("[프로필 없음]\n")
            else:
                print(f"[프로필] {profile.to_prompt_context()}\n")
            continue
        if cmd == "stage":
            print(f"[현재 단계] {LIFECYCLE_METADATA[stage].description}")
            change = input("단계를 변경하시겠습니까? (y/n): ").strip().lower()
            if change == "y":
                stage = ask_lifecycle_stage()
                print(f"\n[단계 변경됨] {LIFECYCLE_METADATA[stage].description}\n")
            continue

        result = graph.invoke(
            {
                "user_question": question,
                "lifecycle_stage": stage.value,
                "messages": memory.get_history(),
            }
        )

        print()
        print(result["final_answer"])
        sources = result.get("sources") or []
        if sources:
            print(f"\n참고: {', '.join(sources)}\n")
        else:
            print()

        memory.add_user_message(question)
        memory.add_ai_message(result["final_answer"])

    print("[chat] 대화를 종료합니다. 건강하십시오.")


if __name__ == "__main__":
    main()
