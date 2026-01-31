import os
import re
import json
import psycopg2
import psycopg2.extras
import google.generativeai as genai
from dotenv import load_dotenv
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

from .state import AgentState
from .schema_context import SCHEMA_CONTEXT

# Pinecone + embeddings
try:
    from pinecone import Pinecone
    from sentence_transformers import SentenceTransformer
    PINECONE_AVAILABLE = True
except Exception:
    PINECONE_AVAILABLE = False

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

pinecone_client = None
document_index = None
embedding_model = None

if PINECONE_AVAILABLE:
    try:
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        document_index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "document-store"))
        embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        print("✅ Pinecone initialized")
    except Exception as e:
        print(f"⚠ Pinecone error: {e}")
        PINECONE_AVAILABLE = False
else:
    print("⚠ Pinecone not available")


def debug(msg: str):
    """Debug logging with timestamp"""
    ts = datetime.now().isoformat()
    print(f"[DEBUG] {ts} | {msg}")


def clean_sql(sql_text: str) -> str:
    """Remove markdown from SQL"""
    return re.sub(r'```(sql|SQL)?', '', sql_text).strip()


def get_context_string(state: AgentState) -> str:
    """Get conversation context with explicit version tracking"""
    history = state.get("conversation_history", [])
    if not history:
        return "No previous context."
    
    lines = ["Recent conversation:"]
    for i, turn in enumerate(history[-3:], 1):
        query = turn.get('query', '')
        route = turn.get('route', '')
        
        # Extract version if present
        version = parse_version_number(query)
        version_tag = f"[Version {version}]" if version else ""
        
        lines.append(f"{i}. {version_tag} {query[:80]}...")
        lines.append(f"   Route: {route}")
    
    return "\n".join(lines)






def parse_version_number(query: str) -> Optional[int]:
    """Extract single version number from query"""
    query_lower = query.lower()
    
    patterns = [
        r'version\s+(\d+)',
        r'ver\s+(\d+)',
        r'v\.\s+(\d+)',
        r'v\s+(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, query_lower)
        if match:
            return int(match.group(1))
    
    return None


def parse_version_range(query: str) -> Optional[Tuple[int, int]]:
    """Extract version range for comparisons"""
    query_lower = query.lower()
    
    if "compare" in query_lower or "between" in query_lower or " to " in query_lower:
        versions = re.findall(r'(?:version|ver|v\.?)\s+(\d+)', query_lower)
        if len(versions) >= 2:
            return (int(versions[0]), int(versions[1]))
    
    return None


def parse_time_filter(query: str) -> Optional[int]:
    """Extract time filter from query"""
    query_lower = query.lower()
    
    if "today" in query_lower:
        return 0
    elif "yesterday" in query_lower:
        return 1
    elif "last week" in query_lower or "this week" in query_lower:
        return 7
    elif "last month" in query_lower or "this month" in query_lower:
        return 30
    
    return None


def parse_uploader_filter(query: str) -> Optional[str]:
    """Extract uploader name from query"""
    query_lower = query.lower()
    
    # Pattern: "by [name]"
    if " by " in query_lower:
        parts = query.split(" by ")
        if len(parts) > 1:
            name = parts[1].strip().split()[0].strip()
            return name
    
    # Pattern: "uploaded by [name]"
    if "uploaded by" in query_lower:
        parts = query.split("uploaded by")
        if len(parts) > 1:
            name = parts[1].strip().split()[0].strip()
            return name
    
    # Pattern: "[name]'s"
    if "'s " in query:
        name = query.split("'s ")[0].split()[-1].strip()
        return name
    
    # Pattern: "from [name]"
    if " from " in query_lower:
        parts = query.split(" from ")
        if len(parts) > 1:
            name = parts[1].strip().split()[0].strip()
            return name
    
    return None


def execute_sql_query(sql: str) -> List[Dict]:
    """Execute SQL and return results"""
    debug(f"Executing SQL:\n{sql}")
    
    if not SUPABASE_DB_URL or not sql:
        debug("DB URL or SQL missing -> returning []")
        return []
    
    conn = None
    try:
        conn = psycopg2.connect(SUPABASE_DB_URL)
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchall()
            debug(f"SQL returned {len(rows)} rows")
            return [dict(r) for r in rows]
    except Exception as e:
        debug(f"❌ SQL Error: {e}")
        return []
    finally:
        if conn:
            conn.close()


def save_to_memory(state: AgentState) -> AgentState:
    """Save query to conversation history"""
    try:
        history = state.get("conversation_history", [])
        if not isinstance(history, list):
            history = []
        
        new_turn = {
            "query": state.get("user_query", ""),
            "response": state.get("response", ""),
            "route": state.get("route", "unknown"),
            "timestamp": datetime.now().isoformat()
        }
        
        history.append(new_turn)
        state["conversation_history"] = history[-5:]
        
        debug(f"Memory saved. History: {len(state['conversation_history'])} turns")
    except Exception as e:
        debug(f"⚠ Memory save failed: {e}")
    
    return state



def llm_classify_query(query: str, context: str) -> Dict[str, Any]:
    """Use LLM to classify query intent with conversation context"""
    
    classification_prompt = f"""
You are a highly precise QUERY INTENT CLASSIFIER. 
Your job is ONLY to classify the user's query intent — NOT to answer the query.

You MUST follow rules strictly.  
You MUST NOT guess or interpret vaguely.  
You MUST classify EXACTLY what the user is asking.

────────────────────────────────────────
USER QUERY (analyze VERY CAREFULLY)
────────────────────────────────────────
"{query}"

────────────────────────────────────────
CONVERSATION CONTEXT (VERY IMPORTANT)
────────────────────────────────────────
{context}

If the context mentions a version number AND the current query uses:
- “this version”
- “that version”
- “same version”
- “it”
You MUST inherit the version_number from the context.

Example:
Previous: “what changed in version 11”  
Current:  “give detailed reason for this version”  
→ version_number = 11 MUST be assigned.

────────────────────────────────────────
SUPER RULE — VERSION + EXPLANATION
────────────────────────────────────────
If the query contains:
• a version number (explicit OR inferred)
AND
• any explanation keyword:
  "reason", "why", "explain", "explanation",
  "detailed", "detailed reason", "cause",
  "what caused", "how come", "describe change"

THEN you MUST classify as:
→ route = "version_hybrid"
→ version_number MUST be set
→ wants_explanation = true
→ needs_reason = true

Do NOT ignore this rule under ANY circumstances.

────────────────────────────────────────
VERSION DIFFERENCE / COMPARISON RULES
(STRONG PRIORITY)
────────────────────────────────────────
The following phrases ALWAYS indicate a VERSION COMPARISON:

• “difference between version X and Y”
• “difference of version X and version Y”
• “difference of X and Y”
• “compare X and Y”
• “compare version X to version Y”
• “changes between X and Y”
• “what changed between version X and Y”
• “how is version X different from version Y”
• “increase from version X to Y”
• “decrease from version X to Y”

When ANY of these patterns are present:
→ route = "version_query"
→ version_range = [min(X,Y), max(X,Y)]
→ wants_explanation = false (unless explanation keywords also exist)
→ version_number MUST NOT be forced (because range exists)

This rule overrides all others EXCEPT the SUPER RULE.

────────────────────────────────────────
FIRST / OLDEST VERSION RULE
────────────────────────────────────────
If the user asks for:
- "first version"
- "oldest version"
- "earliest version"
- "initial version"
- "starting version"

Then:
→ route = "version_query"
→ version_number = 1

ALWAYS assume version 1 is the oldest unless database context overrides.

────────────────────────────────────────
DATABASE INTENT RULES (target_list)
────────────────────────────────────────
If the query refers to ANY HCP data fields:
(hcp_name, full_name, city, gender, specialty, qualification,
hospital_name, email, phone, call_frequency, experience, category,
monthly_sales, therapy_area, designation)

OR if the query asks to “show”, “filter”, “count”, “list” HCPs:

THEN:
→ route = "database_only"

────────────────────────────────────────
HISTORY TABLE RULES (version metadata)
────────────────────────────────────────
If the user refers to:
- version_number
- changed_rows
- total_rows
- operation_type
- reason
- filename
- triggered_by
- document link

THEN:
→ route = "version_query" (unless SUPER RULE applies)

────────────────────────────────────────
DOCUMENT SEARCH RULES
────────────────────────────────────────
If the query asks to search documents:
“search documents”, “find documents”, “find file”, “semantic search”
→ route = "semantic_search"

If the query says:
“documents by <name>”, “uploaded by <name>”
→ route = "version_hybrid"
→ has_uploader_filter = true

────────────────────────────────────────
RAW SQL RULE
────────────────────────────────────────
If the query begins with:
SELECT, UPDATE, DELETE, INSERT, COUNT, WITH

→ route = "database_only"

────────────────────────────────────────
OUTPUT FORMAT — STRICT JSON ONLY
────────────────────────────────────────


Return ONLY valid JSON:

{{
  "route": "<database_only | version_query | version_hybrid | semantic_search>",
  "reasoning": "Brief explanation",
  "confidence": 0.95,
  "version_number": null,
  "version_range": null,
  "wants_explanation": false,
  "needs_reason": false,
  "has_uploader_filter": false,
  "suggested_message": null
}}

Analyze now and return JSON.
"""

    prompt = classification_prompt
    debug(f"Classifier prompt length: {len(prompt)} chars")

    try:
        response = model.generate_content(prompt)
        clean_text = response.text.strip()
        clean_text = clean_text.replace("```json", "").replace("```", "").strip()

        debug(f"Classifier raw output:\n{clean_text}")
        result = json.loads(clean_text)

        # Normalize
        if not isinstance(result, dict):
            raise ValueError("Classifier did not return a JSON object")

        query_lower = query.lower()

        # Extract explicit version number / range
        explicit_version = parse_version_number(query)
        version_range = parse_version_range(query)

        # SUPER RULE — version + explanation
        has_explanation_keyword = any(
            kw in query_lower for kw in
            ["why", "reason", "explain", "explanation", "detailed", "cause", "what happened"]
        )

        if explicit_version and has_explanation_keyword:
            debug("⚠ SUPER RULE → forcing version_hybrid")
            result["route"] = "version_hybrid"
            result["version_number"] = explicit_version
            result["wants_explanation"] = True
            result["needs_reason"] = True
            result["confidence"] = 0.98

        # RULE 9 — FIRST / OLDEST VERSION
        if any(
            kw in query_lower for kw in
            ["first version", "oldest version", "earliest version", "starting version", "initial version"]
        ):
            debug("⚠ RULE 9 → forcing version_number = 1")
            result["route"] = "version_query"
            result["version_number"] = 1
            result["confidence"] = 0.99

        # Preserve version_range if classifier did not fill it
        if version_range and not result.get("version_range"):
            debug(f"Preserving version_range {version_range} from parsing")
            result["version_range"] = version_range

        # Preserve explicit version when classifier didn't return one
        if explicit_version and not result.get("version_number") and not version_range:
            debug(f"Preserving extracted version {explicit_version}")
            result["version_number"] = explicit_version

        return result

    except Exception as e:
        debug(f"❌ Classification error: {e}")
        return {
            "route": "invalid",
            "reasoning": str(e),
            "confidence": 0.0,
            "suggested_message": "Classification failed."
        }



def router_node(state: AgentState) -> AgentState:
    """
    Improved Router with conversation context awareness
    """
    state_copy = dict(state)
    query = state_copy.get("user_query", "")
    query_lower = query.lower().strip()

    print(f"\n{'='*70}")
    print(f"🎯 INTELLIGENT ROUTING (CONTEXT-AWARE)")
    print(f"{'='*70}\n")

    debug(f"Routing Query: {query}")

    # Get conversation history
    history = state_copy.get("conversation_history", [])
    debug(f"📚 Conversation History Length: {len(history)}")

    version_num = parse_version_number(query)
    version_range = parse_version_range(query)
    
    debug(f"🔢 Version from current query: {version_num}")

    context_version = None
    if not version_num and not version_range and history:
        debug("⚠️ No version in current query - checking history...")
        
        # Search through history in reverse (most recent first)
        for turn in reversed(history):
            # Get query text (handle both formats)
            prev_query = turn.get("query") or turn.get("content", "")
            
            # Skip assistant responses
            if turn.get("role") == "assistant" or not prev_query:
                continue
            
            prev_version = parse_version_number(prev_query)
            if prev_version:
                debug(f"✅ Found version {prev_version} in history")
                debug(f"   Previous query was: {prev_query[:80]}")
                context_version = prev_version
                version_num = prev_version
                break
        
        if not context_version:
            debug("❌ No version found in history")

    context = get_context_string(state_copy)
    enhanced_context = context
    
    if version_num:
        source = "current query" if not context_version else "conversation history"
        enhanced_context += f"\n\n🔍 VERSION FROM {source.upper()}: {version_num}"
        debug(f"📌 Enhanced context with version {version_num} from {source}")

    # RAW SQL SHORTCUT
    if query_lower.startswith(("select", "count", "delete", "insert", "update", "with")):
        debug("RAW SQL detected → forcing database_only")
        state_copy["route"] = "database_only"
        state_copy["version_number"] = version_num
        state_copy["version_range"] = version_range
        return state_copy

    # HISTORY TABLE SHORTCUT
    if ("history" in query_lower or
        "history_table" in query_lower or
        "versions are there" in query_lower or
        "how many versions" in query_lower or
        "total versions" in query_lower):
        
        debug("History-table question detected → forcing database_only")
        state_copy["route"] = "database_only"
        state_copy["version_number"] = version_num
        state_copy["version_range"] = version_range
        return state_copy

    uploader = parse_uploader_filter(query)
    if uploader:
        debug(f"Detected uploader filter: {uploader}")

    # CALL LLM CLASSIFIER
    classification = llm_classify_query(query, enhanced_context)
    route = classification.get("route", "invalid").lower()

    debug(f"🤖 LLM Classification Result:")
    debug(f"   Route: {route}")
    debug(f"   Version Number: {classification.get('version_number')}")
    debug(f"   Version Range: {classification.get('version_range')}")

    # ✅ CRITICAL FIX: Preserve version_range from LLM
    llm_version_range = classification.get("version_range")
    if llm_version_range and not version_range:
        debug(f"✅ Using version_range from LLM: {llm_version_range}")
        version_range = llm_version_range
    
    # DO NOT override version_number when version_range exists
    if version_range:
        debug("Version range detected — skipping single-version override")
    else:
        # Only force version_number if LLM did not return any version info
        if version_num and not classification.get("version_number"):
            debug(f"🔧 FORCING single version from parsing: {version_num}")
            classification["version_number"] = version_num

    # SUPER RULE: Version + explanation keywords
    query_lower = query.lower()
    has_explanation_keyword = any(
        kw in query_lower for kw in 
        ["why", "reason", "explain", "explanation", "detailed", "cause", "what happened"]
    )
    
    # If we have a version (from current OR context) + explanation keywords
    # MUST be hybrid
    if version_num and has_explanation_keyword:
        debug("⚠️ SUPER RULE: Version + explanation keywords detected")
        route = "version_hybrid"
        classification["route"] = "version_hybrid"
        classification["version_number"] = version_num
        classification["wants_explanation"] = True
        classification["needs_reason"] = True

    if uploader and route == "semantic_search":
        debug("Uploader filter + semantic → upgrading to hybrid")
        route = "version_hybrid"

    # Validate route
    allowed_routes = ["database_only", "version_query", "version_hybrid", "semantic_search"]
    if route not in allowed_routes:
        debug(f"Invalid route '{route}', defaulting to database_only")
        route = "database_only"

    if route == "hybrid":
        route = "version_hybrid"

    # ✅ FINAL STATE ASSIGNMENT - USE version_range from LLM if available
    state_copy["route"] = route
    state_copy["routing_reason"] = classification.get("reasoning", "")
    state_copy["routing_confidence"] = classification.get("confidence", 0.0)
    state_copy["version_number"] = classification.get("version_number") or version_num
    state_copy["version_range"] = version_range or classification.get("version_range")  # ✅ CRITICAL
    state_copy["wants_explanation"] = classification.get("wants_explanation", False)
    state_copy["needs_reason"] = classification.get("needs_reason", False)
    state_copy["uploader_filter"] = uploader
    state_copy["time_filter"] = parse_time_filter(query)

    debug(f"FINAL ROUTE: {route.upper()}")
    debug(f"FINAL VERSION NUMBER: {state_copy.get('version_number')}")
    debug(f"FINAL VERSION RANGE: {state_copy.get('version_range')}")
    print(f"{'='*70}\n")
    return state_copy

def database_query_node(state: AgentState) -> AgentState:
    """Generate and execute SQL for target_list queries with improved name logic."""
    
    state_copy = dict(state)
    query = state_copy.get("user_query", "")
    context = get_context_string(state_copy)

    print(f"{'='*70}")
    print(f"📊 DATABASE QUERY")
    print(f"{'='*70}\n")

   
    tokens = [t.strip() for t in re.split(r'\s+', query) if len(t.strip()) > 1]
    tokens = [
        t for t in tokens
        if len(t) > 2 and t.lower() not in {"the", "in", "of", "for", "and", "to", "show", "all", "me"}
    ]
    debug(f"Query tokens: {tokens}")
    state_copy["query_tokens"] = tokens


    def build_name_condition(name_tokens: List[str]) -> str:
        """
        Name logic:
          - 1 token  → simple ILIKE
          - 2+ tokens → AND logic (NEVER OR)
        """
        if not name_tokens:
            return ""

        if len(name_tokens) == 1:
            return f"full_name ILIKE '%{name_tokens[0]}%'"

        parts = [f"full_name ILIKE '%{t}%'" for t in name_tokens]
        return " AND ".join(parts)

    # Build name condition if user's query looks like a name search
    name_condition = ""
    if tokens:
        # Detect if tokens are alphabetic (not numbers or SQL keywords)
        if all(t.isalpha() for t in tokens):
            name_condition = build_name_condition(tokens)
            debug(f"Detected name condition: {name_condition}")

    
    sql_prompt = f"""
Generate a PostgreSQL SELECT query for this request.

SCHEMA:
{SCHEMA_CONTEXT}

CONTEXT:
{context}

REQUEST: {query}

TOKENS: {tokens}

RULES:
- Return ONLY pure SQL (no markdown).
- Use exact column names.
- Always use fuzzy matching for strings (ILIKE).
- For person name searches:
    * If 1 token → full_name ILIKE '%token%'
    * If 2+ tokens → full_name ILIKE '%token1%' AND full_name ILIKE '%token2%'
    * NEVER use OR for names.
- Include LIMIT 100.

If "{query}" is a name lookup:
    Use WHERE {name_condition}

ONLY return a valid SQL query.
"""

    debug("Generating SQL for database query")

  
    try:
        response = model.generate_content(sql_prompt)
        sql = clean_sql(response.text)
        debug(f"Generated SQL:\n{sql}")

        # Prevent empty/invalid SQL strings
        if not sql.lower().startswith("select"):
            raise Exception("Invalid SQL returned by LLM")

        results = execute_sql_query(sql)
        state_copy["results"] = results
        state_copy["results_count"] = len(results)
        debug(f"Database node returned {len(results)} rows")

    except Exception as e:
        debug(f"Database node error: {e}")
        state_copy["error"] = str(e)
        state_copy["results"] = []
        state_copy["results_count"] = 0

    print(f"{'='*70}\n")
    return state_copy



def version_query_node(state: AgentState) -> AgentState:
    """Fetch version metadata and calculate diffs"""
    state_copy = dict(state)
    version_num = state_copy.get("version_number")
    version_range = state_copy.get("version_range")
    
    print(f"{'='*70}")
    print(f"📜 VERSION QUERY")
    print(f"{'='*70}\n")
    
    debug(f"version_num={version_num}, version_range={version_range}")
    
    try:
        # PRIORITY 1: Version comparison (range)
        # CHECK THIS FIRST, BEFORE CHECKING version_num
        if version_range and len(version_range) == 2:
            v1, v2 = version_range
            debug(f"🔄 COMPARISON MODE: v{v1} → v{v2}")
            
            sql = f"""
            SELECT h1.version_number as v1_version, h1.total_rows as v1_total_rows,
                   h1.changed_rows as v1_changed_rows, h1.operation_type as v1_operation,
                   h2.version_number as v2_version, h2.total_rows as v2_total_rows,
                   h2.changed_rows as v2_changed_rows, h2.operation_type as v2_operation,
                   (h2.total_rows - h1.total_rows) as row_difference,
                   h2.reason, h2.triggered_by, h2.timestamp, h2.doc_id, h2.filename
            FROM public.history_table h1
            JOIN public.history_table h2 ON h1.table_name = h2.table_name
            WHERE h1.version_number = {v1} AND h2.version_number = {v2}
            ORDER BY h2.timestamp DESC;
            """
            
            results = execute_sql_query(sql)
            state_copy["results"] = results
            state_copy["results_count"] = len(results)
            state_copy["is_comparison"] = True if results else False
            debug(f"✅ Compared versions {v1} and {v2}: {len(results)} rows")
            
            if not results:
                state_copy["error"] = f"Could not compare versions {v1} and {v2}"
        
        # PRIORITY 2: Single version
        elif version_num and not version_range:
            debug(f"📌 SINGLE VERSION MODE: v{version_num}")
            
            sql = f"""
            SELECT version_id, version_number, table_name, total_rows,
                   changed_rows, operation_type, reason, triggered_by,
                   timestamp, doc_id, filename, file_type, num_chunks
            FROM public.history_table
            WHERE version_number = {version_num}
            ORDER BY timestamp DESC
            LIMIT 10;
            """
            
            results = execute_sql_query(sql)
            state_copy["results"] = results
            state_copy["results_count"] = len(results)
            debug(f"✅ Fetched {len(results)} rows for version {version_num}")
            
            if not results:
                state_copy["error"] = f"Version {version_num} not found"
        
        # PRIORITY 3: Latest versions (no version_num or version_range specified)
        else:
            debug("📚 LATEST VERSIONS MODE")
            
            sql = """
            SELECT version_id, version_number, table_name, total_rows,
                   changed_rows, operation_type, reason, triggered_by,
                   timestamp, doc_id, filename, file_type
            FROM public.history_table
            ORDER BY version_id DESC
            LIMIT 5;
            """
            
            results = execute_sql_query(sql)
            state_copy["results"] = results
            state_copy["results_count"] = len(results)
            debug(f"✅ Fetched latest versions: {len(results)} rows")
    
    except Exception as e:
        debug(f"❌ Version query error: {e}")
        state_copy["results"] = []
        state_copy["results_count"] = 0
        state_copy["error"] = str(e)
    
    print(f"{'='*70}\n")
    return state_copy



def version_hybrid_node(state: AgentState) -> AgentState:
    """Combine version metadata + Pinecone documents"""
    state_copy = dict(state)
    version_num = state_copy.get("version_number")
    query = state_copy.get("user_query", "")
    
    print(f"{'='*70}")
    print(f"🔀 VERSION HYBRID SEARCH")
    print(f"{'='*70}\n")
    
    debug(f"Version hybrid node called for version {version_num}")
    
    if not PINECONE_AVAILABLE or not document_index or not embedding_model:
        debug("Pinecone unavailable")
        state_copy["results"] = []
        state_copy["results_count"] = 0
        state_copy["error"] = "Pinecone unavailable"
        print(f"{'='*70}\n")
        return state_copy
    
    try:
        if not version_num:
            state_copy["results"] = []
            state_copy["error"] = "Version number required for hybrid search"
            print(f"{'='*70}\n")
            return state_copy
        
        # Get version metadata
        sql = f"""
        SELECT version_id, version_number, table_name, total_rows,
               changed_rows, operation_type, reason, triggered_by,
               timestamp, doc_id, filename, file_type, num_chunks
        FROM public.history_table
        WHERE version_number = {version_num}
        LIMIT 5;
        """
        
        version_data = execute_sql_query(sql)
        debug(f"Version metadata rows: {len(version_data)}")
        
        if not version_data:
            state_copy["results"] = []
            state_copy["error"] = f"Version {version_num} not found"
            print(f"{'='*70}\n")
            return state_copy
        
        # Extract doc_ids
        doc_ids = [v.get("doc_id") for v in version_data if v.get("doc_id")]
        debug(f"doc_ids linked to version {version_num}: {doc_ids}")
        
        if not doc_ids:
            state_copy["results"] = {
                "version_metadata": version_data,
                "document_matches": [],
                "total_matches": 0
            }
            state_copy["results_count"] = 0
            print(f"{'='*70}\n")
            return state_copy
        
        # Search Pinecone
        q_emb = embedding_model.encode([query]).tolist()[0]
        search_results = document_index.query(
            vector=q_emb,
            top_k=15,
            filter={"doc_id": {"$in": doc_ids}},
            include_metadata=True
        )
        
        debug(f"Pinecone matches: {len(search_results.get('matches', []))}")
        
        # Group by document
        doc_matches = {}
        for match in search_results.get("matches", []):
            md = match.get("metadata", {})
            doc_id = md.get("doc_id")
            
            if not doc_id:
                continue
            
            if doc_id not in doc_matches:
                doc_matches[doc_id] = {
                    "doc_id": doc_id,
                    "filename": md.get("filename", ""),
                    "uploader": md.get("uploader_name", ""),
                    "action": md.get("action", ""),
                    "hcp_name": md.get("hcp_name", ""),
                    "hcp_email": md.get("hcp_email", ""),
                    "change_description": md.get("change_description", ""),
                    "chunks": []
                }
            
            doc_matches[doc_id]["chunks"].append({
                "text": md.get("chunk_text", ""),
                "similarity": match.get("score", 0)
            })
        
        doc_list = list(doc_matches.values())
        state_copy["results"] = {
            "version_metadata": version_data,
            "document_matches": doc_list,
            "total_matches": len(doc_list)
        }
        state_copy["results_count"] = len(doc_list)
        debug(f"Hybrid found {len(doc_list)} documents")
    
    except Exception as e:
        debug(f"Version hybrid error: {e}")
        state_copy["results"] = []
        state_copy["results_count"] = 0
        state_copy["error"] = str(e)
    
    print(f"{'='*70}\n")
    return state_copy



def semantic_search_node(state: AgentState) -> AgentState:
    """Search documents using vector embeddings"""
    state_copy = dict(state)
    query = state_copy.get("user_query", "")
    uploader = state_copy.get("uploader_filter")
    
    print(f"{'='*70}")
    print(f"🔍 SEMANTIC SEARCH")
    print(f"{'='*70}\n")
    
    debug(f"Semantic search: {query}" + (f" (uploader: {uploader})" if uploader else ""))
    
    if not PINECONE_AVAILABLE or not document_index or not embedding_model:
        debug("Pinecone unavailable")
        state_copy["results"] = []
        state_copy["results_count"] = 0
        state_copy["error"] = "Vector search unavailable"
        print(f"{'='*70}\n")
        return state_copy
    
    try:
        # Encode query
        q_emb = embedding_model.encode([query]).tolist()[0]
        debug("Query encoded")
        
        # Build filter if uploader specified
        pinecone_filter = None
        if uploader:
            pinecone_filter = {"uploader_name": {"$eq": uploader}}
            debug(f"Pinecone filter: {pinecone_filter}")
        
        # Search Pinecone
        search_results = document_index.query(
            vector=q_emb,
            top_k=30,
            filter=pinecone_filter,
            include_metadata=True
        )
        
        matches = search_results.get("matches", [])
        debug(f"Semantic search matches: {len(matches)}")
        
        if not matches:
            state_copy["results"] = []
            state_copy["results_count"] = 0
            print(f"{'='*70}\n")
            return state_copy
        
        # Group by document
        docs = {}
        for m in matches:
            md = m.get("metadata", {})
            doc_id = md.get("doc_id")
            
            if not doc_id:
                continue
            
            if doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": md.get("filename", "Unknown"),
                    "uploader": md.get("uploader_name", "Unknown"),
                    "table_name": md.get("table_name", "Unknown"),
                    "action": md.get("action", "Unknown"),
                    "hcp_name": md.get("hcp_name", ""),
                    "hcp_email": md.get("hcp_email", ""),
                    "timestamp": md.get("timestamp", ""),
                    "change_description": md.get("change_description", ""),
                    "chunks": []
                }
            
            docs[doc_id]["chunks"].append({
                "text": md.get("chunk_text", ""),
                "similarity": m.get("score", 0),
                "chunk_index": md.get("chunk_index", 0)
            })
        
        # Sort by similarity
        docs_list = list(docs.values())
        for d in docs_list:
            cs = d["chunks"]
            d["avg_similarity"] = sum(c["similarity"] for c in cs) / len(cs) if cs else 0
        
        docs_list.sort(key=lambda x: x["avg_similarity"], reverse=True)
        docs_list = docs_list[:5]
        
        state_copy["results"] = docs_list
        state_copy["results_count"] = len(docs_list)
        debug(f"Returning {len(docs_list)} documents")
    
    except Exception as e:
        debug(f"Semantic search error: {e}")
        state_copy["results"] = []
        state_copy["results_count"] = 0
        state_copy["error"] = str(e)
    
    print(f"{'='*70}\n")
    return state_copy




def handle_invalid_route(state: AgentState) -> AgentState:
    """Handle queries that couldn't be classified"""
    state_copy = dict(state)
    
    print(f"\n{'='*70}")
    print(f"❌ UNABLE TO CLASSIFY QUERY")
    print(f"{'='*70}\n")
    
    user_query = state_copy.get("user_query", "")
    routing_reason = state_copy.get("routing_reason", "Unclear intent")
    
    print(f"Query: {user_query}")
    print(f"Reason: {routing_reason}\n")
    
    # Build helpful response with suggestions
    suggestion_prompt = f"""
The user asked: "{user_query}"

This query couldn't be understood because: {routing_reason}

Provide a brief, helpful response that:
1. Acknowledges the issue politely
2. Gives 2-3 examples of queries you CAN help with
3. Suggests how they could rephrase their question

Keep it conversational and friendly (2-3 sentences max).
"""
    
    try:
        response = model.generate_content(suggestion_prompt)
        helpful_message = response.text.strip()
        helpful_message = helpful_message.replace("**", "").replace("__", "").replace("```", "")
        state_copy["response"] = helpful_message
        print(f"Suggestion:\n{helpful_message}\n")
    except:
        default_message = """I couldn't understand your query.

Try asking me things like:
- "Show me all HCPs in target list"
- "What changed in version 4?"
- "Compare version 3 and 5"
- "Why did version 5 change?" (with document context)
- "Search documents for quarterly"

Please rephrase and try again!"""
        state_copy["response"] = default_message
        print(f"Response:\n{default_message}\n")
    
    # Save to memory even for invalid queries
    state_copy = save_to_memory(state_copy)
    
    # Ensure response is string
    if not isinstance(state_copy.get("response"), str):
        state_copy["response"] = json.dumps(state_copy["response"], default=str, indent=2)
    
    print(f"{'='*70}\n")
    
    return state_copy



def summarizer_node(state: AgentState) -> AgentState:
    """
    Format results into natural language based on route.
    """

    state_copy = dict(state)
    route = state_copy.get("route", "unknown")
    results = state_copy.get("results", [])
    query = state_copy.get("user_query", "")
    error = state_copy.get("error")
    results_count = state_copy.get("results_count", 0)
    is_comparison = state_copy.get("is_comparison", False)

    print(f"\n{'='*70}")
    print(f"📝 SUMMARIZER - Route: {route.upper()}")
    print(f"{'='*70}\n")

    # Error case
    if error:
        response = f"❌ Error: {error}\n\nPlease try rephrasing your query."
        state_copy["response"] = response
        print(response)
        return state_copy

    # No results
    if not results or results_count == 0:
        response = "❌ No results found. Please try rephrasing your query."
        state_copy["response"] = response
        print(response)
        return state_copy

    # ───────────────────────────────────────────────────────────────
    # ROUTE: DATABASE ONLY
    # ───────────────────────────────────────────────────────────────
    if route == "database_only":
        rows = results

        # 1) LLM Summary
        data_for_llm = json.dumps(rows[:20], default=str, indent=2)

        summarization_prompt = f"""
You are a data analyst. The user asked: "{query}"

Database returned {results_count} results:

{data_for_llm}

Summarize this data BRIEFLY in natural language:
- What does this data show?
- What are the key insights?
- Any patterns or notable points?

Keep it concise (3-5 sentences max). Be conversational, NOT a bullet list.
"""

        debug(f"LLM summarizing {results_count} database rows")

        try:
            llm_response = model.generate_content(summarization_prompt)
            summary = llm_response.text.strip().replace("**", "").replace("__", "")
            debug("LLM summary generated")

        except Exception as e:
            debug(f"Summarization failed: {e}, using fallback")
            summary = fallback_summary(rows, results_count, query)

        # 2) Pretty formatting
        pretty = [
            "📊 SUMMARY",
            "─" * 50,
            summary,
            "",
            "",
            "📋 DETAILED RECORDS",
            "─" * 50,
            f"Total: {results_count} record(s)\n",
        ]

        for i, row in enumerate(rows, 1):
            title = (
                row.get("full_name")
                or row.get("hcp_name")
                or row.get("name")
                or f"Record {i}"
            )
            pretty.append(f"#{i} — {title}")

            for key, value in row.items():
                if key.lower() in ["full_name", "hcp_name", "name"]:
                    continue
                pretty.append(f"   • {key.replace('_', ' ').title()}: {value}")

            pretty.append("")

        response = "\n".join(pretty)
        state_copy["response"] = response
        print(response)
        return state_copy

    # ───────────────────────────────────────────────────────────────
    # ROUTE: VERSION QUERY
    # ───────────────────────────────────────────────────────────────
    if route == "version_query":
        if is_comparison:
            comp = results[0]
            response = f"""
📊 VERSION COMPARISON

From Version {comp.get('v1_version')} → To Version {comp.get('v2_version')}

ROWS:
  Before: {comp.get('v1_total_rows', 0):,}
  After:  {comp.get('v2_total_rows', 0):,}
  Change: {comp.get('row_difference', 0):+,}

CHANGES IN VERSION {comp.get('v2_version')}:
  Operation: {comp.get('operation_type')}
  Changed Rows: {comp.get('changes_in_v2')}
  Triggered By: {comp.get('triggered_by')}
  Timestamp: {comp.get('timestamp')}

REASON:
{comp.get('reason', 'Not specified')}

{f"📄 Document: {comp.get('filename')}" if comp.get('filename') else ""}
"""
        else:
            v = results[0]
            response = f"""
📜 VERSION {v.get('version_number')} DETAILS

TABLE: {v.get('table_name')}

STATISTICS:
  Total Rows: {v.get('total_rows', 0):,}
  Changed Rows: {v.get('changed_rows', 0):,}
  Operation: {v.get('operation_type')}

INFO:
  Triggered By: {v.get('triggered_by')}
  Timestamp: {v.get('timestamp')}

REASON:
{v.get('reason', 'Not specified')}

{f"📄 Document: {v.get('filename')}" if v.get('filename') else ""}
{f"   Chunks: {v.get('num_chunks')}" if v.get('num_chunks') else ""}
"""
        state_copy["response"] = response
        print(response)
        return state_copy

    # ───────────────────────────────────────────────────────────────
    # ROUTE: VERSION HYBRID
    # ───────────────────────────────────────────────────────────────
    if route == "version_hybrid":
        if isinstance(results, dict):
            response_parts = []
            version_meta = results.get("version_metadata", [])
            doc_matches = results.get("document_matches", [])

            if version_meta:
                v = version_meta[0]
                response_parts += [
                    f"📜 VERSION {v.get('version_number')} - DETAILED BREAKDOWN\n",
                    "WHAT CHANGED:",
                    f"  • Total Rows: {v.get('total_rows', 0):,}",
                    f"  • Changed Rows: {v.get('changed_rows', 0):,}",
                    f"  • Operation: {v.get('operation_type')}",
                    f"  • Triggered By: {v.get('triggered_by')}",
                    f"  • When: {v.get('timestamp')}\n",
                    "REASON:",
                    v.get("reason", "Not specified"),
                    "",
                ]

            if doc_matches:
                response_parts.append(f"📁 SUPPORTING DOCUMENTS ({len(doc_matches)} found):\n")
                for i, doc in enumerate(doc_matches[:3], 1):
                    filename = doc.get("filename", "Unknown")
                    uploader = doc.get("uploader", "Unknown")
                    action = doc.get("action", "N/A")
                    hcp_name = doc.get("hcp_name", "")
                    chunks = doc.get("chunks", [])

                    response_parts.append(f"{i}. {filename}")
                    response_parts.append(f"   Uploaded By: {uploader} | Action: {action}")
                    if hcp_name:
                        response_parts.append(f"   Subject: {hcp_name}")

                    if chunks:
                        best = max(chunks, key=lambda x: x.get("similarity", 0))
                        sim = int(best.get("similarity", 0) * 100)
                        text = best.get("text", "")[:800]
                        response_parts.append(f"   Match [{sim}%]: {text}...")
                    response_parts.append("")
            else:
                response_parts.append("📁 No supporting documents found.")

            response = "\n".join(response_parts)
        else:
            response = "Error formatting hybrid results."

        state_copy["response"] = response
        print(response)
        return state_copy

    # ───────────────────────────────────────────────────────────────
    # ROUTE: SEMANTIC SEARCH
    # ───────────────────────────────────────────────────────────────
    if route == "semantic_search":
        parts = [f"🔍 FOUND {results_count} DOCUMENTS\n"]

        for i, doc in enumerate(results[:5], 1):
            filename = doc.get("filename", "Unknown")
            uploader = doc.get("uploader", "Unknown")
            action = doc.get("action", "")
            hcp_name = doc.get("hcp_name", "")
            avg_sim = doc.get("avg_similarity", 0)
            chunks = doc.get("chunks", [])

            parts.append(f"{i}. 📄 {filename} ({int(avg_sim * 100)}% match)")
            parts.append(f"   Uploaded by: {uploader}")
            if action:
                parts.append(f"   Action: {action}")
            if hcp_name:
                parts.append(f"   Subject: {hcp_name}")

            for chunk in chunks[:2]:
                text = chunk.get("text", "")[:750]
                sim = int(chunk.get("similarity", 0) * 100)
                parts.append(f"   [{sim}%] {text}...")
            parts.append("")

        response = "\n".join(parts)
        state_copy["response"] = response
        print(response)
        return state_copy

    # ───────────────────────────────────────────────────────────────
    # UNKNOWN ROUTE
    # ───────────────────────────────────────────────────────────────
    response = f"Unknown route: {route}. Please try rephrasing."
    state_copy["response"] = response
    print(response)
    return state_copy


def fallback_summary(rows: List[Dict], total_count: int, query: str) -> str:
    """Fallback summary if LLM fails"""

    if not rows:
        return "No records found."

    sample = rows[0]

    names = [
        row.get("full_name") or row.get("hcp_name") or row.get("name")
        for row in rows[:5]
        if row.get("full_name") or row.get("hcp_name") or row.get("name")
    ]

    summary_parts = []

    if total_count == 1:
        summary_parts.append("Found 1 record matching your query.")
    else:
        summary_parts.append(f"Found {total_count} records matching your query.")

    if names:
        if len(names) <= 3:
            summary_parts.append(f"Top results: {', '.join(names)}")
        else:
            summary_parts.append(
                f"Top results include: {', '.join(names[:3])}, and {len(names)-3} more"
            )

    for key in sample.keys():
        if any(m in key.lower() for m in ["count", "total", "sales", "frequency", "calls"]):
            val = sample.get(key)
            if val:
                summary_parts.append(f"{key.replace('_',' ').title()}: {val}")

    return " | ".join(summary_parts)




def execute_query(state: AgentState) -> AgentState:
    """
    Complete workflow:
    query → route → execute → summarize → response
    """
    print(f"\n{'='*70}")
    print(f"🚀 PROCESSING QUERY: {state.get('user_query', '')}")
    print(f"{'='*70}\n")
    
    debug(f"Processing incoming query: {state.get('user_query', '')}")
    
    # Step 1: Route
    state = router_node(state)
    
    # Step 2: Check if invalid - if so, return
    if state.get("route") == "invalid":
        debug("Route is invalid, calling handle_invalid_route...")
        state = handle_invalid_route(state)
        return state
    
    # Step 3: Execute based on valid route
    route = state.get("route")
    
    if route == "database_only":
        state = database_query_node(state)
    elif route == "version_query":
        state = version_query_node(state)
    elif route == "version_hybrid":
        state = version_hybrid_node(state)
    elif route == "semantic_search":
        state = semantic_search_node(state)
    else:
        debug(f"Unknown route: {route}")
        state["response"] = "An unexpected error occurred. Please try again."
        return state
    
    # Step 4: Summarize results
    state = summarizer_node(state)
    
    # Step 5: Save to memory
    state = save_to_memory(state)
    
    debug("Execution complete, returning response")
    return state


if __name__ == "__main__":
    print("✅ nodes.py loaded successfully")