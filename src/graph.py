"""Build the LangGraph state machine that routes by intent and lifecycle stage.

Graph layout:

                  classify_intent
                        |
        +---------------+---------------+----------------+
        |               |               |                |
   emergency     medical_disclaimer    rag (diet)    rag (general)
        |               |               |                |
       END             END           generate         generate
                                        |                |
                                       END              END

Edges out of ``rag`` always go to ``generate``. The conditional fan-out from
``classify_intent`` is the only place intent affects routing.
"""

from langchain_chroma import Chroma
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent_state import AgentState
from src.nodes import (
    classify_intent_node,
    emergency_response_node,
    generate_response_node,
    medical_disclaimer_node,
    rag_node,
)
from src.rag_chain import (
    build_lifecycle_generation,
    build_medical_disclaimer_generation,
    build_rag_chain,
)
from src.user_profile import UserProfile


def build_lifecycle_graph(
    vectorstore: Chroma,
    user_profile: UserProfile | None = None,
) -> CompiledStateGraph:
    """Assemble and compile the lifecycle-aware LangGraph.

    The retrieval LCEL chain and the two generation runnables are constructed
    once and captured in node closures so each invocation reuses them.
    """
    components = build_rag_chain(vectorstore, user_profile=user_profile)
    lifecycle_gen = build_lifecycle_generation()
    medical_gen = build_medical_disclaimer_generation()

    workflow = StateGraph(AgentState)

    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("rag", lambda s: rag_node(s, components))
    workflow.add_node(
        "generate",
        lambda s: generate_response_node(s, lifecycle_gen, user_profile),
    )
    workflow.add_node("emergency", emergency_response_node)
    workflow.add_node(
        "medical_disclaimer",
        lambda s: medical_disclaimer_node(s, components, medical_gen, user_profile),
    )

    workflow.set_entry_point("classify_intent")
    workflow.add_conditional_edges(
        "classify_intent",
        lambda state: state["intent"],
        {
            "emergency": "emergency",
            "medical_advice": "medical_disclaimer",
            "diet_advice": "rag",
            "general": "rag",
        },
    )
    workflow.add_edge("rag", "generate")
    workflow.add_edge("generate", END)
    workflow.add_edge("emergency", END)
    workflow.add_edge("medical_disclaimer", END)

    return workflow.compile()
