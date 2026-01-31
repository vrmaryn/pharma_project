"""
Complete LangGraph State - Version Hybrid System
================================================
Supports 5 execution paths:
- database_only (target_list)
- version_query (history_table)
- version_hybrid (history_table + Pinecone)
- semantic_search (Pinecone)
- invalid (error handling)
"""

from typing import TypedDict, Optional, List, Dict, Any, Annotated, Tuple
import operator


class AgentState(TypedDict, total=False):
    """
    Complete state for version-hybrid system.
    All fields are optional (total=False) for flexible initialization.
    """
    
    # =========================================================================
    # INPUT (from user)
    # =========================================================================
    user_query: str
    """The original query from the user"""
    
    
    # =========================================================================
    # ROUTING DECISION (set by router_node)
    # =========================================================================
    route: str
    """
    Route determined by LLM router:
    - "database_only" → Query target_list table
    - "version_query" → Query version history from history_table
    - "version_hybrid" → Combine version metadata + Pinecone documents
    - "semantic_search" → Search Pinecone for documents
    - "invalid" → Query couldn't be classified
    """
    
    routing_reason: str
    """Explanation of why this route was chosen"""
    
    routing_confidence: float
    """Confidence score (0.0-1.0) of the routing decision"""
    
    
    # =========================================================================
    # VERSION-SPECIFIC FIELDS (set by router_node)
    # =========================================================================
    version_number: Optional[int]
    """Single version number if mentioned in query (e.g., 4 from "version 4")"""
    
    version_range: Optional[Tuple[int, int]]
    """Version range for comparisons (e.g., [3, 5] from "compare version 3 and 5")"""
    
    is_comparison: bool
    """Flag indicating if user wants to compare two versions"""
    
    wants_explanation: bool
    """Flag: user wants WHY/REASON/EXPLANATION + documents"""
    
    wants_document_context: bool
    """Flag: user wants document context with version info"""
    
    needs_reason: bool
    """Flag: user explicitly asks for reasons"""
    
    
    # =========================================================================
    # FILTER FIELDS (extracted by router_node)
    # =========================================================================
    time_filter: Optional[int]
    """Time filter in days (0=today, 1=yesterday, 7=last week, 30=last month)"""
    
    uploader_filter: Optional[str]
    """Uploader name filter for hybrid searches"""
    
    doc_id_filter: Optional[str]
    """Specific doc_id filter if user mentions a particular document"""
    
    
    results: Any
    """
    Results from execution node. Format varies by route:
    
    - database_only: List[Dict] - rows from target_list
    - version_query: List[Dict] - version metadata rows
    - version_hybrid: Dict with keys:
        {
            "version_metadata": List[Dict],
            "document_matches": List[Dict],
            "total_matches": int
        }
    - semantic_search: List[Dict] - grouped documents with chunks
    - invalid: [] (empty)
    """
    
    results_count: int
    """Total number of results returned"""
    
    comparison_result: Optional[Dict]
    """For version comparisons: diff data between versions"""
    
    
    # =========================================================================
    # EXECUTION DETAILS
    # =========================================================================
    sql: Optional[str]
    """Generated SQL query (for database_only and version_query routes)"""
    
    sql_executed: bool
    """Whether SQL was successfully executed"""
    
    affected_rows: int
    """Number of rows affected by operation"""
    
    
    # =========================================================================
    # RESPONSE GENERATION (set by summarizer_node)
    # =========================================================================
    response: str
    """
    Final formatted response to user.
    Can be:
    - Natural language summary
    - JSON (for raw output requests)
    - Helpful error message (for invalid queries)
    """
    
    response_format: str
    """Format of response: "natural_language" | "json" | "error_message" """
    
    
    # =========================================================================
    # MEMORY - Conversation History (append-only, last 5 turns)
    # =========================================================================
    conversation_history: Annotated[List[Dict[str, Any]], operator.add]
    """
    Conversation memory tracking last 5 turns.
    
    Each turn contains:
    {
        "query": str,           # User's query
        "response": str,        # Bot's response
        "route": str,           # Route taken
        "timestamp": str        # ISO timestamp
    }
    
    Annotated with operator.add for automatic list append in LangGraph.
    """
    
    
    # =========================================================================
    # CONTENT FOCUS (set by router_node)
    # =========================================================================
    content_focus: str
    """
    What user is looking for:
    - "metadata" - version numbers, row counts, dates
    - "documents" - file content, explanations
    - "operations" - INSERT/UPDATE/DELETE details
    - "diffs" - changes between versions
    - "reasons" - why something changed
    """
    
    
    # =========================================================================
    # ERROR HANDLING
    # =========================================================================
    error: Optional[str]
    """Error message if operation failed"""
    
    error_type: str
    """Type of error: "routing_error" | "execution_error" | "parsing_error" | "rate_limit" """
    
    error_recovery: str
    """What should happen next: "retry" | "fallback_to_semantic" | "ask_user_to_rephrase" """
    
    
    # =========================================================================
    # DEBUG/METADATA
    # =========================================================================
    execution_time_ms: float
    """Time taken for query execution in milliseconds"""
    
    pinecone_queries_used: int
    """Number of Pinecone queries executed"""
    
    database_queries_used: int
    """Number of database queries executed"""
    
    debug_mode: bool
    """Enable detailed logging and debugging"""


# =========================================================================
# STATE INITIALIZATION HELPERS
# =========================================================================

def create_initial_state(user_query: str, debug: bool = False) -> AgentState:
    """
    Create initial state for a new query.
    
    Args:
        user_query: The user's input query
        debug: Enable debug mode
    
    Returns:
        Initialized AgentState
    """
    return {
        "user_query": user_query,
        "conversation_history": [],
        "debug_mode": debug,
        "results": [],
        "results_count": 0,
        "affected_rows": 0,
        "pinecone_queries_used": 0,
        "database_queries_used": 0,
        "sql_executed": False,
        "is_comparison": False,
        "wants_explanation": False,
        "wants_document_context": False,
        "needs_reason": False,
        "response_format": "natural_language",
        "error_type": "",
        "error_recovery": ""
    }


def merge_states(old_state: AgentState, new_state: Dict) -> AgentState:
    """
    Merge new state updates into existing state.
    Handles list appending for conversation_history.
    
    Args:
        old_state: Previous state
        new_state: New updates to merge
    
    Returns:
        Merged state
    """
    merged = dict(old_state)
    
    for key, value in new_state.items():
        if key == "conversation_history" and isinstance(value, list):
            # For conversation history, append instead of replace
            existing = merged.get("conversation_history", [])
            merged["conversation_history"] = existing + value
        else:
            # For other fields, replace
            merged[key] = value
    
    return merged


# =========================================================================
# STATE VALIDATION
# =========================================================================

def validate_state(state: AgentState) -> tuple[bool, str]:
    """
    Validate that state has required fields and valid values.
    
    Args:
        state: State to validate
    
    Returns:
        (is_valid: bool, error_message: str)
    """
    # Check required fields
    if "user_query" not in state or not state["user_query"]:
        return False, "Missing user_query"
    
    if "route" in state and state["route"] not in [
        "database_only", "version_query", "version_hybrid", 
        "semantic_search", "invalid", ""
    ]:
        return False, f"Invalid route: {state['route']}"
    
    if "response_format" in state and state["response_format"] not in [
        "natural_language", "json", "error_message"
    ]:
        return False, f"Invalid response_format: {state['response_format']}"
    
    if "results_count" in state and state["results_count"] < 0:
        return False, "results_count cannot be negative"
    
    if "routing_confidence" in state:
        conf = state["routing_confidence"]
        if not (0.0 <= conf <= 1.0):
            return False, f"routing_confidence must be 0.0-1.0, got {conf}"
    
    return True, ""


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🔧 AGENT STATE STRUCTURE")
    print("="*70 + "\n")
    
    # Create sample state
    sample_state = create_initial_state("What changed in version 4?")
    print("✅ Created initial state")
    print(f"   Query: {sample_state['user_query']}")
    print(f"   Route: {sample_state.get('route', 'unrouted')}")
    print(f"   Results: {sample_state['results_count']} rows\n")
    
    # Validate state
    is_valid, error = validate_state(sample_state)
    print(f"✅ State validation: {'PASS' if is_valid else 'FAIL'}")
    if error:
        print(f"   Error: {error}")
    
    print("\n" + "="*70 + "\n")