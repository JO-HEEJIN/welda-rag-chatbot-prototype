"""CLI chat interface for the Welda RAG chatbot powered by the lifecycle graph."""

import itertools
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Quiet the noisy HuggingFace Hub "unauthenticated" warning at the source —
# environment variables must be set BEFORE huggingface_hub is imported, and
# logger levels are then tightened for the loaders that still emit warnings.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
for noisy in ("huggingface_hub", "huggingface_hub.utils._http", "transformers"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

from pydantic import ValidationError  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.messages import AIMessageChunk  # noqa: E402

from src.conversation_memory import ConversationManager  # noqa: E402
from src.graph import build_lifecycle_graph  # noqa: E402
from src.lifecycle import LIFECYCLE_METADATA, LifecycleStage  # noqa: E402
from src.rag_chain import load_vector_store  # noqa: E402
from src.user_profile import UserProfile  # noqa: E402


SPINNER_FRAMES = ["✽", "✾", "✿", "❀", "❁", "❀", "✿", "✾"]

NODE_LABELS: dict[str, str] = {
    "classify_intent": "의도 분류 중",
    "extract_constraints": "사용자 규칙 추출 중",
    "food_extraction": "음식 식별 중",
    "graph_lookup": "도메인 그래프 조회 중",
    "rag": "관련 문서 검색 중",
    "generate": "응답 생성 중 (필요 시 웹 검색 포함)",
    "emergency": "응급 안내 준비 중",
    "medical_disclaimer": "의료 정보 정리 중",
}


class Spinner:
    """Background spinner that overwrites its line until ``stop()`` is called.

    Designed for the CLI's "before the first token" gap: while ``graph.stream``
    is still inside non-LLM nodes (intent classification, graph lookup, RAG,
    or the early portion of generate before tokens stream), this keeps the
    user from seeing a blank screen. The label can be updated mid-flight as
    LangGraph fires ``updates`` events for each completed node.
    """

    def __init__(self, label: str = "준비 중"):
        self._label = label
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._active = False

    def set_label(self, label: str) -> None:
        with self._lock:
            self._label = label

    def start(self) -> None:
        if self._active:
            return
        self._stop.clear()
        self._active = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if not self._active:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.3)
        self._thread = None
        self._active = False
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    def _run(self) -> None:
        frames = itertools.cycle(SPINNER_FRAMES)
        while not self._stop.is_set():
            with self._lock:
                label = self._label
            frame = next(frames)
            sys.stdout.write(f"\r\033[K{frame} {label}…")
            sys.stdout.flush()
            time.sleep(0.12)

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


def _chunk_text(content) -> str:
    """Extract printable text from an AIMessageChunk content payload.

    When the underlying LLM has the Anthropic ``web_search`` tool attached,
    streamed chunks arrive with ``content`` as a list of block dicts (text /
    server_tool_use / web_search_tool_result). Without the tool, ``content``
    is a plain string. Pull just the text portions in either case.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return ""


def stream_graph_response(graph, initial_state: dict) -> tuple[str, list[str]]:
    """Stream the LangGraph response with a status spinner until the first token.

    ``stream_mode=["updates", "messages", "values"]`` runs three streams in one
    pass: ``updates`` tells us which node just finished (so we can refresh the
    spinner label), ``messages`` yields the LLM token chunks (so we can stop
    the spinner the moment the first text arrives), and ``values`` yields each
    node's resulting state (so we can pick up ``sources`` and the hardcoded
    emergency ``final_answer``).

    Spinner / streaming handoff: while a non-LLM node is running, the spinner
    line is overwritten in place with the current node's Korean label. Once
    the first text token arrives, the spinner clears itself and the rest of
    the response prints normally. This matches what users expect from
    agentic CLIs — visible progress during the long graph-lookup + web-search
    stretches that would otherwise look frozen for 20+ seconds.
    """
    full_response = ""
    final_state: dict | None = None
    streamed_any_tokens = False
    spinner = Spinner(label="준비 중")
    spinner.start()

    try:
        for stream_mode, payload in graph.stream(
            initial_state, stream_mode=["updates", "messages", "values"]
        ):
            if stream_mode == "updates":
                if isinstance(payload, dict):
                    for node_name in payload:
                        label = NODE_LABELS.get(node_name, node_name)
                        spinner.set_label(label)
            elif stream_mode == "messages":
                chunk, _metadata = payload
                if isinstance(chunk, AIMessageChunk):
                    text = _chunk_text(chunk.content)
                    if text:
                        if not streamed_any_tokens:
                            spinner.stop()
                        print(text, end="", flush=True)
                        full_response += text
                        streamed_any_tokens = True
            elif stream_mode == "values":
                final_state = payload
    finally:
        spinner.stop()

    print()

    if not streamed_any_tokens and final_state:
        answer = final_state.get("final_answer", "")
        if answer:
            print(answer)
            full_response = answer

    sources = list(final_state.get("sources") or []) if final_state else []
    return full_response, sources


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

    # First-launch setup is dominated by the BGE-M3 embedding load (~2.27 GB
    # into RAM). Spin the cursor while we wait so the user sees progress
    # instead of a silent ~5-10 s gap before the prompt appears.
    setup_spinner = Spinner(label="임베딩 모델 로드 중")
    setup_spinner.start()
    try:
        vectorstore = load_vector_store(str(persist_dir))
        setup_spinner.set_label("그래프 초기화 중")
        graph = build_lifecycle_graph(vectorstore, user_profile=profile)
    finally:
        setup_spinner.stop()
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

        print()
        full_response, sources = stream_graph_response(
            graph,
            {
                "user_question": question,
                "lifecycle_stage": stage.value,
                "messages": memory.get_history(),
            },
        )

        if sources:
            print(f"\n참고: {', '.join(sources)}\n")
        else:
            print()

        memory.add_user_message(question)
        memory.add_ai_message(full_response)

    print("[chat] 대화를 종료합니다. 건강하십시오.")


if __name__ == "__main__":
    main()
