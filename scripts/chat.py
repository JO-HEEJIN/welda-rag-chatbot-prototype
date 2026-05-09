"""CLI chat interface for the Welda RAG chatbot with profile + memory."""

import sys
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.conversation_memory import ConversationManager
from src.rag_chain import build_rag_chain, load_vector_store
from src.user_profile import UserProfile

DIET_GOAL_CHOICES = {
    "1": "weight_loss",
    "2": "blood_sugar_control",
    "3": "muscle_gain",
    "4": "maintenance",
}

INSULIN_LEVEL_CHOICES = {"1": "low", "2": "moderate", "3": "high"}

GENDER_CHOICES = {"1": "male", "2": "female", "3": "other"}


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

    print("[chat] Welda 혈당 관리 코치 CLI 데모입니다.")
    print("[chat] 명령: exit/quit (종료), reset (메모리 초기화), history (대화 기록), profile (프로필 보기)\n")

    profile: UserProfile | None = None
    answer = input("사용자 프로필을 설정하시겠습니까? (y/n): ").strip().lower()
    if answer == "y":
        profile = build_profile_interactively()
        print(f"\n[프로필 저장됨] {profile.to_prompt_context()}\n")
    else:
        print("[프로필 없이 진행]\n")

    vectorstore = load_vector_store(str(persist_dir))
    chain = build_rag_chain(vectorstore, user_profile=profile)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
    memory = ConversationManager(max_turns=10)

    while True:
        try:
            question = input(">>> ").strip()
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

        docs = retriever.invoke(question)
        sources = sorted({d.metadata.get("source_file", "unknown") for d in docs})

        answer_text = chain.invoke(
            {"question": question, "chat_history": memory.get_history()}
        )
        memory.add_user_message(question)
        memory.add_ai_message(answer_text)

        print(f"\n{answer_text}\n")
        print(f"참고: {', '.join(sources)}\n")

    print("[chat] 대화를 종료합니다. 건강하십시오.")


if __name__ == "__main__":
    main()
