"""Sliding-window conversation memory wrapping LangChain's in-memory store."""

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


class ConversationManager:
    """Keep the most recent ``max_turns`` user/AI exchanges in memory.

    One turn equals one user message plus one AI message, so the manager retains
    at most ``max_turns * 2`` messages. When the limit is exceeded, the oldest
    messages are dropped first (sliding window). No persistence, no vector
    recall — short-term context only, which is enough for a CLI demo and easy to
    explain in an interview.
    """

    def __init__(self, max_turns: int = 10) -> None:
        self.max_turns = max_turns
        self._history = InMemoryChatMessageHistory()

    def add_user_message(self, content: str) -> None:
        self._history.add_user_message(content)
        self._enforce_limit()

    def add_ai_message(self, content: str) -> None:
        self._history.add_ai_message(content)
        self._enforce_limit()

    def get_history(self) -> list[BaseMessage]:
        return list(self._history.messages)

    def clear(self) -> None:
        self._history.clear()

    def get_history_as_text(self) -> str:
        """Plain-text dump for debugging or 'history' CLI command."""
        lines: list[str] = []
        for msg in self._history.messages:
            if isinstance(msg, HumanMessage):
                role = "사용자"
            elif isinstance(msg, AIMessage):
                role = "코치"
            else:
                role = msg.type
            lines.append(f"[{role}] {msg.content}")
        return "\n".join(lines)

    def _enforce_limit(self) -> None:
        max_messages = self.max_turns * 2
        if len(self._history.messages) > max_messages:
            self._history.messages = self._history.messages[-max_messages:]
