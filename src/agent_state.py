"""LangGraph AgentState shared across nodes in the lifecycle state machine."""

from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """Shared mutable state passed between LangGraph nodes.

    ``messages`` uses the ``add`` reducer so each node can append without
    overwriting prior turns. All other fields are last-write-wins. ``total=False``
    so nodes only need to populate the keys they update.
    """

    messages: Annotated[list[BaseMessage], add]
    user_question: str
    user_profile_dict: dict
    lifecycle_stage: str
    intent: str
    retrieved_context: str
    sources: list[str]
    final_answer: str

    # Block 7 GraphRAG fields
    food_query: str
    graph_context: str
    graph_found: bool
    graph_sources: list[str]
    used_web_search: bool

    # Block 8 user-stated constraints (accumulated across turns)
    user_constraints: Annotated[list[str], add]
