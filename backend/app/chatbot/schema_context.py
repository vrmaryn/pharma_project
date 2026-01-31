

SCHEMA_CONTEXT = """
================================================================
🧠 SYSTEM OVERVIEW
================================================================
This system powers a **Healthcare Professional (HCP) Management and
Version Tracking Platform** designed to store, query, analyze, and
audit changes made to doctor (HCP) records over time.

The platform maintains two major data assets:

1. **HCP Master List (target_list)**  
   A comprehensive dataset of healthcare professionals containing:
   - Personal and professional details  
   - Hospital affiliations  
   - Specialties and therapy areas  
   - Influence metrics  
   - Sales contribution (monthly/yearly)  
   - Interaction history  
   - Engagement priority  

2. **Version & Change Log (history_table)**  
   A historical audit trail capturing:
   - Data changes (INSERT, UPDATE, DELETE)  
   - Row counts before and after changes  
   - Change reasons and user who triggered them  
   - Timestamps and version numbers  
   - Supporting metadata (documents/chunks if uploaded)  

----------------------------------------------------------------
🎯 PURPOSE OF THE SYSTEM
----------------------------------------------------------------
The system enables accurate reporting, analytics, tracking, and
querying of HCP records and their evolution over time. Its SQL engine
responds to natural-language queries by generating optimized
PostgreSQL SELECT statements tailored to the user's intent.

The database allows answering questions such as:

- Which doctors exist in the current master list?
- Who requested a change and what was modified?
- How many HCPs belong to a particular specialty, city, or category?
- Which HCPs contribute the most to sales?
- What interactions occurred recently?
- How many versions exist and what triggered each one?
- Which deletions or updates occurred for a given time range?
- What is the distribution of experience, influence, and priorities?

----------------------------------------------------------------
🔍 SUPPORTED QUERY THEMES
----------------------------------------------------------------
- **HCP Discovery & Filtering**  
  (e.g., find cardiologists, female consultants, top influencers)

- **Sales & Performance Analytics**  
  (totals, averages, rankings, breakdowns)

- **Interaction & Activity Tracking**  
  (recent calls, last interaction dates, frequency analysis)

- **Versioning & Change Audits**  
  (view logs, see deleted entries, analyze reasons for change)

- **Metadata Insights**  
  (who triggered a version, how many rows changed, files associated)

----------------------------------------------------------------
🧩 HOW THE MODEL USES THIS OVERVIEW
----------------------------------------------------------------
This overview helps the SQL generator:
- Understand the purpose of the database  
- Map user intent to the correct table  
- Know which domain each table belongs to  
- Determine when a question relates to versions vs. HCP data  
- Produce precise, context-aware SQL queries  

================================================================
END OF SYSTEM OVERVIEW
================================================================

================================================================
🏗️ CORE TABLES AND THEIR PURPOSES
================================================================
DATABASE SCHEMA + SQL INSTRUCTIONS CONTEXT
==========================================

You are given two PostgreSQL tables: target_list and history_table.
Use them to generate ONLY PostgreSQL SELECT queries based on user requests.


{
  "tables": {
    "target_list": {
      "description": "Main HCP data table containing doctor records.",
      "columns": {
        "hcp_id": {
          "type": "integer",
          "synonyms": ["id", "doctor id", "hcp code", "code", "unique id"],
          "meaning": "Unique identifier for an HCP"
        },
        "full_name": {
          "type": "text",
          "synonyms": ["name", "doctor name", "hcp name", "physician name"],
          "meaning": "Full name of the HCP"
        },
        "specialty": {
          "type": "text",
          "synonyms": ["department", "specialisation", "field", "practice area"],
          "meaning": "Medical specialty of the HCP"
        },
        "email": {
          "type": "text",
          "synonyms": ["email id", "mail", "email address"],
          "meaning": "Email address of the HCP"
        },
        "phone": {
          "type": "text",
          "synonyms": ["contact", "phone number", "mobile number"],
          "meaning": "Phone number of the HCP"
        },
        "city": {
          "type": "text",
          "synonyms": ["location", "place", "area"],
          "meaning": "City where the HCP practices"
        }
      },
      "natural_queries": [
        "Show all HCPs",
        "How many doctors?",
        "List all records in target list",
        "Count entries in target list"
      ]
    },

    "history_table": {
      "description": "Version control table tracking every change to target_list.",
      "columns": {
        "version_id": {
          "type": "integer",
          "synonyms": ["vid", "version id", "internal id"],
          "meaning": "Primary key for version history entries"
        },
        "version_number": {
          "type": "integer",
          "synonyms": ["version", "v", "ver", "v number"],
          "meaning": "Version number of the update"
        },
        "operation_type": {
          "type": "text",
          "synonyms": ["operation", "type", "insert or delete", "what happened", "change type"],
          "meaning": "INSERT, UPDATE, or DELETE"
        },
        "table_name": {
          "type": "text",
          "synonyms": ["table", "target table"],
          "meaning": "Name of the table affected (usually target_list)"
        },
        "total_rows": {
          "type": "integer",
          "synonyms": [
            "total", "total records", "total entries", "row count", 
            "number of rows", "how many rows", "count", "size"
          ],
          "meaning": "Total number of rows in the table after the version update"
        },
        "changed_rows": {
          "type": "integer",
          "synonyms": [
            "changes", "modified rows", "updated rows", "how many changed", 
            "difference", "rows affected"
          ],
          "meaning": "Number of rows changed in this version"
        },
        "reason": {
          "type": "text",
          "synonyms": ["why", "reason for change", "explanation", "cause"],
          "meaning": "Reason for the change as provided by the system or user"
        },
        "triggered_by": {
          "type": "text",
          "synonyms": ["who updated", "who changed", "user", "performed by", "updated by"],
          "meaning": "Name of the person/system that made the change"
        },
        "timestamp": {
          "type": "timestamp",
          "synonyms": ["when", "date", "time", "when updated", "update time"],
          "meaning": "When the version update was performed"
        },
        "doc_id": {
          "type": "text",
          "synonyms": ["document id", "doc id", "file id"],
          "meaning": "Identifier of the document related to this version"
        },
        "filename": {
          "type": "text",
          "synonyms": ["file", "document", "doc name", "file name"],
          "meaning": "Name of the document that triggered the version change"
        },
        "file_type": {
          "type": "text",
          "synonyms": ["file extension", "type", "doc type"],
          "meaning": "Type of file (e.g., .pdf, .docx)"
        },
        "num_chunks": {
          "type": "integer",
          "synonyms": ["chunks", "number of chunks", "vector chunks"],
          "meaning": "How many vector chunks were created for the document"
        }
      },
      "natural_queries": [
        "What changed in version X?",
        "How many rows in version 5?",
        "Explain version 10",
        "Compare version 4 and version 9",
        "Why was version 8 updated?"
      ]
    }
  }
}


------------------------------------------------
TABLE: target_list
------------------------------------------------
Description:
Stores detailed information about Healthcare Professionals (HCPs), including
name, specialty, hospital details, influence score, experience, sales, 
interaction data, and priority classification.

Columns:
- id                       SERIAL PRIMARY KEY
- hcp_code                 TEXT UNIQUE
- full_name                TEXT NOT NULL
- gender                   TEXT CHECK (male/female/other)
- qualification            TEXT
- specialty                TEXT
- designation              TEXT
- email                    TEXT
- phone                    TEXT
- hospital_name            TEXT
- hospital_address         TEXT
- city                     TEXT
- state                    TEXT
- pincode                  TEXT
- experience_years         INTEGER
- influence_score          NUMERIC(5,2)
- category                 TEXT
- therapy_area             TEXT
- monthly_sales            INTEGER
- yearly_sales             INTEGER
- last_interaction_date    DATE
- call_frequency           INTEGER
- priority                 BOOLEAN DEFAULT FALSE

Representative Rows:
1 | HCP001 | Dr. Rohan Mehta | male | Cardiology | Senior Consultant | Noida | UP | 12 yrs | 4.80 | A | 120000 | 1450000 | 2024-10-15 | 3 | true
2 | HCP002 | Dr. Sneha Kapoor | female | Gynecology | Consultant | Delhi | Delhi | 8 yrs | 4.30 | B | 70000 | 820000 | 2024-09-25 | 2 | false
51 | NULL | Karan Malhotra | male | Psychiatry | Consultant | NIMHANS | NULL | 8 yrs | 4.20 | NULL | 60000 | 720000 | 2024-10-02 | NULL | true


------------------------------------------------
TABLE: history_table
------------------------------------------------
Description:
Version log storing audit information for INSERT, UPDATE, DELETE operations
performed on any table. Primarily tracks target_list changes.

Columns:
- version_id        BIGSERIAL PRIMARY KEY
- version_number    INTEGER NOT NULL
- operation_type    TEXT CHECK ('INSERT','UPDATE','DELETE')
- table_name        TEXT NOT NULL
- total_rows        INTEGER
- changed_rows      INTEGER
- reason            TEXT
- triggered_by      TEXT DEFAULT 'Administrator'
- timestamp         TIMESTAMP DEFAULT NOW()
- doc_id            TEXT
- filename          TEXT
- file_type         TEXT
- num_chunks        INTEGER

Representative Rows:
1 | 1 | DELETE | target_list | 14 | 1 | Manual delete: Dr. Vivek Sinha | Administrator | 2025-11-16
2 | 2 | DELETE | target_list | 12 | 2 | Manual bulk delete (2 HCPs)    | Administrator | 2025-11-16


================================================
SQL QUERY LOGIC & CASE TYPES
================================================

You must classify the user's request into one of the following SQL categories and generate the matching query.

NOTE:
- ALWAYS produce PostgreSQL SELECT queries only.
- NEVER modify data.
- NEVER hallucinate columns.

------------------------------------------------
CASE TYPE 1: SIMPLE RETRIEVAL
------------------------------------------------
User intent: "show", "list", "display", "get all"

Examples:
Q: Show all HCPs.
SQL:
SELECT * FROM target_list;

Q: Show names and emails.
SQL:
SELECT full_name, email FROM target_list;


------------------------------------------------
CASE TYPE 2: FILTERED QUERIES
------------------------------------------------
User intent: "where", "with", "having", "greater than", "less than"

Examples:
Q: Doctors with influence score > 4.5.
SQL:
SELECT full_name, specialty, influence_score
FROM target_list
WHERE influence_score > 4.5;

Q: Female HCPs from Delhi.
SQL:
SELECT full_name, gender, city
FROM target_list
WHERE gender = 'female' AND city = 'Delhi';


------------------------------------------------
CASE TYPE 3: SORTING & LIMITING
------------------------------------------------
User intent: "top", "highest", "lowest", "sorted"

Examples:
Q: Top 5 doctors by yearly sales.
SQL:
SELECT full_name, yearly_sales
FROM target_list
ORDER BY yearly_sales DESC
LIMIT 5;


------------------------------------------------
CASE TYPE 4: AGGREGATION / GROUPING
------------------------------------------------
User intent: "count", "total", "sum", "average", "group by", "distribution"

Examples:
Q: Total yearly sales per specialty.
SQL:
SELECT specialty, SUM(yearly_sales) AS total_yearly_sales
FROM target_list
GROUP BY specialty;

Q: Count of HCPs by city.
SQL:
SELECT city, COUNT(*) AS count
FROM target_list
GROUP BY city;


------------------------------------------------
CASE TYPE 5: DATE-BASED QUERIES
------------------------------------------------
User intent: "recent", "before", "after", "latest", "recently contacted"

Examples:
Q: HCPs contacted after Oct 1 2024.
SQL:
SELECT full_name, last_interaction_date
FROM target_list
WHERE last_interaction_date > '2024-10-01';

Q: 5 most recent interactions.
SQL:
SELECT full_name, last_interaction_date
FROM target_list
ORDER BY last_interaction_date DESC
LIMIT 5;


------------------------------------------------
CASE TYPE 6: HISTORY / VERSION QUERIES
------------------------------------------------
User intent: "versions", "history", "logs", "deletions", "changes", "audit"

Examples:
Q: Show all delete operations in target_list.
SQL:
SELECT *
FROM history_table
WHERE table_name = 'target_list'
  AND operation_type = 'DELETE'
ORDER BY timestamp DESC;

Q: Latest version update.
SQL:
SELECT *
FROM history_table
WHERE table_name = 'target_list'
ORDER BY version_number DESC
LIMIT 1;


------------------------------------------------
CASE TYPE 7: COMPLEX MULTI-CONDITION
------------------------------------------------
Examples:
Q: Female consultants with influence > 4.5 in Delhi.
SQL:
SELECT full_name, specialty, influence_score
FROM target_list
WHERE gender = 'female'
  AND influence_score > 4.5
  AND city = 'Delhi'
  AND designation LIKE '%Consultant%';


------------------------------------------------
CASE TYPE 8: SPECIAL RULES
------------------------------------------------
- Never use data not defined in schema.
- If user asks for a non-existing column, return an SQL comment:
  -- Error: column does not exist.
- Always assume null-safe comparisons logically.
- Strings must be single-quoted.
- Date formats must be ISO: YYYY-MM-DD.


================================================
END OF SCHEMA CONTEXT
================================================
DATABASE SCHEMA + SQL INSTRUCTIONS CONTEXT
==========================================

You are given two PostgreSQL tables: target_list and history_table.
Use them to generate ONLY PostgreSQL SELECT queries based on user requests.

------------------------------------------------
TABLE: target_list
------------------------------------------------
Description:
Stores detailed information about Healthcare Professionals (HCPs), including
name, specialty, hospital details, influence score, experience, sales, 
interaction data, and priority classification.

Columns:
- id                       SERIAL PRIMARY KEY
- hcp_code                 TEXT UNIQUE
- full_name                TEXT NOT NULL
- gender                   TEXT CHECK (male/female/other)
- qualification            TEXT
- specialty                TEXT
- designation              TEXT
- email                    TEXT
- phone                    TEXT
- hospital_name            TEXT
- hospital_address         TEXT
- city                     TEXT
- state                    TEXT
- pincode                  TEXT
- experience_years         INTEGER
- influence_score          NUMERIC(5,2)
- category                 TEXT
- therapy_area             TEXT
- monthly_sales            INTEGER
- yearly_sales             INTEGER
- last_interaction_date    DATE
- call_frequency           INTEGER
- priority                 BOOLEAN DEFAULT FALSE

Representative Rows:
1 | HCP001 | Dr. Rohan Mehta | male | Cardiology | Senior Consultant | Noida | UP | 12 yrs | 4.80 | A | 120000 | 1450000 | 2024-10-15 | 3 | true
2 | HCP002 | Dr. Sneha Kapoor | female | Gynecology | Consultant | Delhi | Delhi | 8 yrs | 4.30 | B | 70000 | 820000 | 2024-09-25 | 2 | false
51 | NULL | Karan Malhotra | male | Psychiatry | Consultant | NIMHANS | NULL | 8 yrs | 4.20 | NULL | 60000 | 720000 | 2024-10-02 | NULL | true


------------------------------------------------
TABLE: history_table
------------------------------------------------
Description:
Version log storing audit information for INSERT, UPDATE, DELETE operations
performed on any table. Primarily tracks target_list changes.

Columns:
- version_id        BIGSERIAL PRIMARY KEY
- version_number    INTEGER NOT NULL
- operation_type    TEXT CHECK ('INSERT','UPDATE','DELETE')
- table_name        TEXT NOT NULL
- total_rows        INTEGER
- changed_rows      INTEGER
- reason            TEXT
- triggered_by      TEXT DEFAULT 'Administrator'
- timestamp         TIMESTAMP DEFAULT NOW()
- doc_id            TEXT
- filename          TEXT
- file_type         TEXT
- num_chunks        INTEGER

Representative Rows:
1 | 1 | DELETE | target_list | 14 | 1 | Manual delete: Dr. Vivek Sinha | Administrator | 2025-11-16
2 | 2 | DELETE | target_list | 12 | 2 | Manual bulk delete (2 HCPs)    | Administrator | 2025-11-16


================================================
SQL QUERY LOGIC & CASE TYPES
================================================

You must classify the user's request into one of the following SQL categories and generate the matching query.

NOTE:
- ALWAYS produce PostgreSQL SELECT queries only.
- NEVER modify data.
- NEVER hallucinate columns.

------------------------------------------------
CASE TYPE 1: SIMPLE RETRIEVAL
------------------------------------------------
User intent: "show", "list", "display", "get all"

Examples:
Q: Show all HCPs.
SQL:
SELECT * FROM target_list;

Q: Show names and emails.
SQL:
SELECT full_name, email FROM target_list;


------------------------------------------------
CASE TYPE 2: FILTERED QUERIES
------------------------------------------------
User intent: "where", "with", "having", "greater than", "less than"

Examples:
Q: Doctors with influence score > 4.5.
SQL:
SELECT full_name, specialty, influence_score
FROM target_list
WHERE influence_score > 4.5;

Q: Female HCPs from Delhi.
SQL:
SELECT full_name, gender, city
FROM target_list
WHERE gender = 'female' AND city = 'Delhi';


------------------------------------------------
CASE TYPE 3: SORTING & LIMITING
------------------------------------------------
User intent: "top", "highest", "lowest", "sorted"

Examples:
Q: Top 5 doctors by yearly sales.
SQL:
SELECT full_name, yearly_sales
FROM target_list
ORDER BY yearly_sales DESC
LIMIT 5;


------------------------------------------------
CASE TYPE 4: AGGREGATION / GROUPING
------------------------------------------------
User intent: "count", "total", "sum", "average", "group by", "distribution"

Examples:
Q: Total yearly sales per specialty.
SQL:
SELECT specialty, SUM(yearly_sales) AS total_yearly_sales
FROM target_list
GROUP BY specialty;

Q: Count of HCPs by city.
SQL:
SELECT city, COUNT(*) AS count
FROM target_list
GROUP BY city;


------------------------------------------------
CASE TYPE 5: DATE-BASED QUERIES
------------------------------------------------
User intent: "recent", "before", "after", "latest", "recently contacted"

Examples:
Q: HCPs contacted after Oct 1 2024.
SQL:
SELECT full_name, last_interaction_date
FROM target_list
WHERE last_interaction_date > '2024-10-01';

Q: 5 most recent interactions.
SQL:
SELECT full_name, last_interaction_date
FROM target_list
ORDER BY last_interaction_date DESC
LIMIT 5;


------------------------------------------------
CASE TYPE 6: HISTORY / VERSION QUERIES
------------------------------------------------
User intent: "versions", "history", "logs", "deletions", "changes", "audit"

Examples:
Q: Show all delete operations in target_list.
SQL:
SELECT *
FROM history_table
WHERE table_name = 'target_list'
  AND operation_type = 'DELETE'
ORDER BY timestamp DESC;

Q: Latest version update.
SQL:
SELECT *
FROM history_table
WHERE table_name = 'target_list'
ORDER BY version_number DESC
LIMIT 1;


------------------------------------------------
CASE TYPE 7: COMPLEX MULTI-CONDITION
------------------------------------------------
Examples:
Q: Female consultants with influence > 4.5 in Delhi.
SQL:
SELECT full_name, specialty, influence_score
FROM target_list
WHERE gender = 'female'
  AND influence_score > 4.5
  AND city = 'Delhi'
  AND designation LIKE '%Consultant%';


------------------------------------------------
CASE TYPE 8: SPECIAL RULES
------------------------------------------------
- Never use data not defined in schema.
- If user asks for a non-existing column, return an SQL comment:
  -- Error: column does not exist.
- Always assume null-safe comparisons logically.
- Strings must be single-quoted.
- Date formats must be ISO: YYYY-MM-DD.


================================================
END OF SCHEMA CONTEXT
================================================


"""
