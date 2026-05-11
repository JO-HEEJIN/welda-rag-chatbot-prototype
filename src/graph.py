"""Build the LangGraph state machine that combines intent routing + GraphRAG.

Graph layout (Block 7 Part 3):

                       classify_intent
                              |
        +---------------------+-------------------+
        |                     |                   |
   emergency      medical_disclaimer       food_extraction
        |                     |                   |   (diet_advice / general 공통 수렴)
       END                   END             graph_lookup
                                                  |
                                                 rag
                                                  |
                                            generate_or_fallback
                                                  |
                                                 END

The diet_advice and general intents share the same retrieval + GraphRAG fan-in;
the conditional edge sends both to ``food_extraction``. The fallback LLM
inside ``generate_or_fallback_node`` has Anthropic's server-side ``web_search``
tool attached, so it can fill in the closed-world gap when the graph and
vector store don't carry the user's food / concept.
"""

from langchain_chroma import Chroma
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent_state import AgentState
from src.nodes import (
    classify_intent_node,
    emergency_response_node,
    food_extraction_node,
    generate_or_fallback_node,
    graph_lookup_node,
    medical_disclaimer_node,
    rag_node,
)
from src.rag_chain import (
    build_medical_disclaimer_generation,
    build_rag_chain,
)
from src.user_profile import UserProfile


def build_lifecycle_graph(
    vectorstore: Chroma,
    user_profile: UserProfile | None = None,
) -> CompiledStateGraph:
    """Assemble and compile the lifecycle + GraphRAG state machine.

    ``user_profile`` is captured in node closures so each ``graph.invoke`` /
    ``graph.stream`` call reuses the same profile-bound prompts. The retrieval
    LCEL chain and the medical-disclaimer generator are likewise constructed
    once and shared across invocations.
    """
    components = build_rag_chain(vectorstore, user_profile=user_profile)
    medical_gen = build_medical_disclaimer_generation()

    workflow = StateGraph(AgentState)

    workflow.add_node("classify_intent", classify_intent_node)
    workflow.add_node("food_extraction", food_extraction_node)
    workflow.add_node("graph_lookup", graph_lookup_node)
    workflow.add_node("rag", lambda s: rag_node(s, components))
    workflow.add_node(
        "generate",
        lambda s: generate_or_fallback_node(s, user_profile),
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
            "diet_advice": "food_extraction",
            "general": "food_extraction",
        },
    )
    workflow.add_edge("food_extraction", "graph_lookup")
    workflow.add_edge("graph_lookup", "rag")
    workflow.add_edge("rag", "generate")
    workflow.add_edge("generate", END)
    workflow.add_edge("emergency", END)
    workflow.add_edge("medical_disclaimer", END)

    return workflow.compile()
