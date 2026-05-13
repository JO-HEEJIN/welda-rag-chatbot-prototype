"""Build the LangGraph state machine that combines intent routing + GraphRAG.

Graph layout (Block 8, with emergency bypass):

                       classify_intent  (rule-based)
                              |
              +---------------+----------------+
              |                                |
         (emergency)                     (others)
              |                                |
              |                       extract_constraints   (Haiku 4.5)
              |                                |
              |             +------------------+------------------+
              |             |                  |                  |
              |     medical_disclaimer   food_extraction (diet_advice/general 공통)
              |             |                  |
              |            END           graph_lookup
              |                                |
              |                               rag
              |                                |
              |                       generate_or_fallback
              |                                |
              +---------> emergency           END
                              |
                             END

Emergency intent bypasses ``extract_constraints`` so an in-crisis user gets
the 119/응급실 안내instantly (~0.003 s, no LLM call). Every other intent
flows through ``extract_constraints`` first: the extractor pulls user-stated
standing rules ("앞으로 X 쓰지마") off the latest utterance and the
add-reducer on ``AgentState.user_constraints`` accumulates them across turns.
Every downstream LLM prompt renders the accumulated list at the top of its
instructions so the model can't quietly drop a rule between turns.

The diet_advice and general intents share the same retrieval + GraphRAG fan-in.
The fallback LLM inside ``generate_or_fallback_node`` has Anthropic's
server-side ``web_search`` tool attached, so it can fill in the closed-world
gap when the graph and vector store don't carry the user's food / concept.
"""

from langchain_chroma import Chroma
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agent_state import AgentState
from src.nodes import (
    classify_intent_node,
    emergency_response_node,
    extract_user_constraints_node,
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
    workflow.add_node("extract_constraints", extract_user_constraints_node)
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
    # Emergency bypasses extract_constraints — an in-crisis user must hit
    # the 119/응급실 안내 instantly, with no LLM-extractor overhead in front.
    workflow.add_conditional_edges(
        "classify_intent",
        lambda state: "emergency" if state["intent"] == "emergency" else "extract_constraints",
        {
            "emergency": "emergency",
            "extract_constraints": "extract_constraints",
        },
    )
    workflow.add_conditional_edges(
        "extract_constraints",
        lambda state: state["intent"],
        {
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
