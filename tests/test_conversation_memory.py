"""Tests for the ConversationManager sliding-window memory."""

import sys
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.conversation_memory import ConversationManager


def test_add_and_get_history() -> None:
    manager = ConversationManager(max_turns=5)
    manager.add_user_message("안녕하세요")
    manager.add_ai_message("안녕하십니까. 무엇을 도와드릴까요?")

    history = manager.get_history()
    assert len(history) == 2
    assert isinstance(history[0], HumanMessage)
    assert history[0].content == "안녕하세요"
    assert isinstance(history[1], AIMessage)


def test_sliding_window_drops_oldest() -> None:
    manager = ConversationManager(max_turns=2)
    for i in range(4):
        manager.add_user_message(f"질문 {i}")
        manager.add_ai_message(f"답변 {i}")

    history = manager.get_history()
    assert len(history) == 4  # max_turns=2 -> 4 messages
    assert history[0].content == "질문 2"
    assert history[-1].content == "답변 3"


def test_clear_empties_history() -> None:
    manager = ConversationManager()
    manager.add_user_message("test")
    manager.add_ai_message("ok")
    manager.clear()

    assert manager.get_history() == []
    assert manager.get_history_as_text() == ""


def test_history_as_text_labels_roles() -> None:
    manager = ConversationManager()
    manager.add_user_message("혈당이 뭔가요")
    manager.add_ai_message("포도당 농도입니다")

    text = manager.get_history_as_text()
    assert "[사용자] 혈당이 뭔가요" in text
    assert "[코치] 포도당 농도입니다" in text
