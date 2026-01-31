"""
State Machine - Version Hybrid 4-Path Execution Flow (Clean + Production Ready)
==============================================================================

START → ROUTER → [4 Execution Paths] → SUMMARIZER → END

Execution Paths:
1. database_only    → Query target_list using SQL
2. version_query    → Query history_table for version metadata / diffs
3. version_hybrid   → Version metadata + Pinecone documents
4. semantic_search  → Document content search via Pinecone
5. invalid          → Graceful error handler

All paths → SUMMARIZER → END
"""

from langgraph.graph import StateGraph, START, END
from .nodes import (
    router_node,
    database_query_node,
    version_query_node,
    version_hybrid_node,
    semantic_search_node,
    handle_invalid_route,
    summarizer_node
)
from .state import AgentState




def build_agent_graph():
    """
    Build the version-hybrid state machine used by the chatbot.
    This is the ONLY graph used (no retry logic, as per your request).

    Flow:
        ROUTER → (database/version/hybrid/semantic/invalid) → SUMMARIZER → END
    """

    graph = StateGraph(AgentState)

    # -------------------------------------------
    # ADD NODES
    # -------------------------------------------

    # 1. Router - LLM-based classifier
    graph.add_node("ROUTER", router_node)

    # 2. Actual execution nodes (4 main routes)
    graph.add_node("DATABASE_QUERY", database_query_node)
    graph.add_node("VERSION_QUERY", version_query_node)
    graph.add_node("VERSION_HYBRID", version_hybrid_node)
    graph.add_node("SEMANTIC_SEARCH", semantic_search_node)

    # 3. Invalid handler
    graph.add_node("INVALID_HANDLER", handle_invalid_route)

    # 4. Summarizer
    graph.add_node("SUMMARIZER", summarizer_node)

    # -------------------------------------------
    # INITIAL ROUTE
    # -------------------------------------------
    graph.add_edge(START, "ROUTER")

    # -------------------------------------------
    # CONDITIONAL ROUTING AFTER "ROUTER"
    # -------------------------------------------
    def route_after_classifier(state: AgentState) -> str:
        """
        The ROUTER node stores a string in state["route"].
        Based on that route, we choose which execution node runs next.
        """

        route = (state.get("route") or "").lower()

        if route == "database_only":
            return "DATABASE_QUERY"

        elif route == "version_query":
            return "VERSION_QUERY"

        elif route == "version_hybrid":
            return "VERSION_HYBRID"

        elif route == "semantic_search":
            return "SEMANTIC_SEARCH"

        elif route == "invalid":
            return "INVALID_HANDLER"

        # Fallback (should never happen)
        return "INVALID_HANDLER"

    graph.add_conditional_edges(
        "ROUTER",
        route_after_classifier,
        {
            "DATABASE_QUERY": "DATABASE_QUERY",
            "VERSION_QUERY": "VERSION_QUERY",
            "VERSION_HYBRID": "VERSION_HYBRID",
            "SEMANTIC_SEARCH": "SEMANTIC_SEARCH",
            "INVALID_HANDLER": "INVALID_HANDLER"
        }
    )

    
    graph.add_edge("DATABASE_QUERY", "SUMMARIZER")
    graph.add_edge("VERSION_QUERY", "SUMMARIZER")
    graph.add_edge("VERSION_HYBRID", "SUMMARIZER")
    graph.add_edge("SEMANTIC_SEARCH", "SUMMARIZER")
    graph.add_edge("INVALID_HANDLER", "SUMMARIZER")

 
    graph.add_edge("SUMMARIZER", END)

    return graph.compile()




if __name__ == "__main__":
    print("\n" + "="*70)
    print("🔧 BUILDING VERSION-HYBRID STATE MACHINE")
    print("="*70)

    graph = build_agent_graph()

    print("\nFlow Mapping:")
    print("  START → ROUTER → DATABASE_QUERY     → SUMMARIZER → END")
    print("  START → ROUTER → VERSION_QUERY      → SUMMARIZER → END")
    print("  START → ROUTER → VERSION_HYBRID     → SUMMARIZER → END")
    print("  START → ROUTER → SEMANTIC_SEARCH    → SUMMARIZER → END")
    print("  START → ROUTER → INVALID_HANDLER    → SUMMARIZER → END")

    print("\n✅ Graph compiled successfully\n")
