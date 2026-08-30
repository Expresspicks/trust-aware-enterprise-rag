from typing import TypedDict, Optional
from decimal import Decimal
import json
import re

from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, START, END

from config import LLM_CONFIG
from sql_tools import list_tables, get_table_schema, run_sql



class AgentState(TypedDict, total=False):
    question: str
    user_id: int

    role: Optional[str]
    region: Optional[str]

    tables: Optional[str]
    schema: Optional[str]

    sql_query: Optional[str]
    sql_result: Optional[str]

    error: Optional[str]
    retries: int
    max_retries: int

    final_answer: Optional[str]


def get_llm():
    return ChatGroq(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        temperature=0
    )
    
def clean_sql_output(sql_text: str) -> str:
    """Clean LLM output and keep only one SQL statement."""
    if not sql_text:
        return ""

    sql_text = sql_text.strip()
    sql_text = sql_text.replace("```sql", "").replace("```", "").strip()

    match = re.search(r"\b(SELECT|WITH|SHOW|DESCRIBE|DESC)\b", sql_text, re.IGNORECASE)
    if match:
        sql_text = sql_text[match.start():].strip()

    if ";" in sql_text:
        sql_text = sql_text.split(";")[0].strip() + ";"

    return sql_text  


def make_json_safe(value):
    """Convert MySQL/Python objects such as Decimal into JSON-safe values."""
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    if isinstance(value, list):
        return [make_json_safe(item) for item in value]

    if isinstance(value, dict):
        return {key: make_json_safe(val) for key, val in value.items()}

    return value


def format_sql_result(sql_result, max_chars=5000) -> str:
    """
    Convert SQL result into compact JSON text for the answer-generation LLM.
    This avoids sending huge Python/Decimal objects into the prompt.
    """
    safe_result = make_json_safe(sql_result)

    try:
        result_text = json.dumps(safe_result, ensure_ascii=False, indent=2)
    except TypeError:
        result_text = str(safe_result)

    if len(result_text) > max_chars:
        result_text = (
            result_text[:max_chars]
            + "\n...[SQL result truncated because it was too large]..."
        )

    return result_text



  

def list_tables_node(state: AgentState) -> AgentState:
    tables = list_tables()

    return {
        **state,
        "tables": ", ".join(tables)
    }

def get_schema_node(state: AgentState) -> AgentState:
    tables = list_tables()
    schema_parts = []

    for table in tables:
        schema = get_table_schema(table)
        schema_parts.append(f"\nTable: {table}\nSchema: {schema}")

    return {
        **state,
        "schema": "\n".join(schema_parts)
    }


def generate_sql_node(state: AgentState) -> AgentState:
    llm = get_llm()

    prompt = f"""
You are a careful MySQL assistant.

Your job is to write ONE valid MySQL read-only query based on the user question.

Return rules:
- Return ONLY SQL.
- Do not include markdown.
- Do not include explanation.
- Generate read-only queries only.
- Do not generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE, REPLACE, GRANT, or REVOKE.
- Never use SELECT *.
- Never return raw rows when the question asks for count, total, approved, denied, rate, highest, lowest, top, average, sum, or comparison.
- If the question asks "how many", use COUNT, SUM, AVG, or GROUP BY. Do not list raw column values.
- If the question contains both database and report/document parts, generate SQL only for the structured database part.

User context:
- Role: {state.get("role")}
- Region: {state.get("region")}

Dataset selection:
- Use finance table for sales, customers, month, year, region, expenses, business finance questions.
- Use amazon_access_train for employee access requests, approvals, denials, approval rate, denial rate, resources, managers, departments, role codes, role titles, and role families.
- Do not use amazon_access_test for approved or denied questions because it does not contain ACTION.

Amazon access dataset meaning:
- amazon_access_train contains employee access request records.
- ACTION = 1 means access approved.
- ACTION = 0 means access denied.
- RESOURCE is requested resource ID.
- MGR_ID is manager ID.
- ROLE_DEPTNAME, ROLE_TITLE, ROLE_FAMILY_DESC, ROLE_FAMILY, ROLE_CODE, ROLE_ROLLUP_1, and ROLE_ROLLUP_2 describe employee role/access attributes.

Mandatory Amazon patterns:
- Approved and denied count:
SELECT
    SUM(CASE WHEN ACTION = 1 THEN 1 ELSE 0 END) AS approved_requests,
    SUM(CASE WHEN ACTION = 0 THEN 1 ELSE 0 END) AS denied_requests
FROM amazon_access_train;

- Total access requests:
SELECT COUNT(*) AS total_requests
FROM amazon_access_train;

- Approval rate:
SELECT ROUND(AVG(ACTION) * 100, 2) AS approval_rate_percentage
FROM amazon_access_train;

- Denial rate:
SELECT ROUND((1 - AVG(ACTION)) * 100, 2) AS denial_rate_percentage
FROM amazon_access_train;

- Top/highest resource, manager, department, role code, role title, or role family:
Use the grouped column, COUNT(*) AS total_count, GROUP BY grouped column, ORDER BY total_count DESC, and LIMIT.

Finance dataset rules:
- If the finance table contains multiple rows per region/month/year, use SUM(sales) for total sales.
- If the user asks for total sales for a region/year/month, include SUM(sales) AS total_sales.
- If the user asks for total customers, include SUM(no_of_customer) AS total_customers.
- If the user asks for highest sales by region in a year, use SUM(sales), GROUP BY region, ORDER BY total_sales DESC, and LIMIT 1.
- If the user asks for highest, lowest, total, figure, amount, value, average, sum, or comparison, include the numeric value in the SELECT output.
- For role-limited users, access control is checked later by the backend. Still generate a correct read-only query from the question.

Examples:
Question: How many access requests were approved and how many were denied?
SQL:
SELECT
    SUM(CASE WHEN ACTION = 1 THEN 1 ELSE 0 END) AS approved_requests,
    SUM(CASE WHEN ACTION = 0 THEN 1 ELSE 0 END) AS denied_requests
FROM amazon_access_train;

Question: Which resource received the highest number of access requests?
SQL:
SELECT RESOURCE, COUNT(*) AS total_count
FROM amazon_access_train
GROUP BY RESOURCE
ORDER BY total_count DESC
LIMIT 1;

Question: What is the total sales of NSW?
SQL:
SELECT SUM(sales) AS total_sales
FROM finance
WHERE region = 'NSW';

Question: Which region has the highest sales in 2025?
SQL:
SELECT region, SUM(sales) AS total_sales
FROM finance
WHERE year = 2025
GROUP BY region
ORDER BY total_sales DESC
LIMIT 1;

User question:
{state.get("question")}

Available tables:
{state.get("tables")}

Schema:
{state.get("schema")}

Previous error:
{state.get("error")}

SQL:
"""

    response = llm.invoke(prompt)
    sql_query = clean_sql_output(response.content)

    return {
        **state,
        "sql_query": sql_query,
    }
    
    
def execute_sql_node(state: AgentState) -> AgentState:
    try:
        print("\nSQL BEFORE EXECUTION:")
        print(state.get("sql_query"))

        result = run_sql(state.get("sql_query", ""))

        if isinstance(result, dict) and "error" in result:
            return {
                **state,
                "sql_result": None,
                "error": result["error"],
                "retries": state.get("retries", 0) + 1,
            }

        return {
            **state,
            "sql_result": format_sql_result(result),
            "error": None,
        }

    except Exception as e:
        return {
            **state,
            "sql_result": None,
            "error": str(e),
            "retries": state.get("retries", 0) + 1,
        }


def route_after_execution(state: AgentState) -> str:
    if state.get("error") is None:
        return "generate_answer"

    if state.get("retries", 0) < state.get("max_retries", 3):
        return "generate_sql"

    return "fail"



def generate_answer_node(state: AgentState) -> AgentState:
    llm = get_llm()

    sql_result_text = state.get("sql_result") or ""

    prompt = f"""
You are a helpful enterprise data assistant.

Given the user question, SQL query, and SQL result, write a short and accurate natural language answer.

Rules:
- Use ONLY the SQL result.
- The SQL result is JSON text.
- If SQL result contains a JSON object or list with values, it is NOT empty.
- Do not say "no matching data was found" unless SQL result is empty, [], null, None, or contains no rows.
- If SQL result contains approved_requests and denied_requests, directly state both numbers.
- If SQL result contains total_requests, directly state the total requests.
- If SQL result contains approval_rate_percentage or denial_rate_percentage, directly state the percentage.
- If SQL result contains total_sales, directly state the total sales figure.
- If SQL result contains total_customers, directly state the total customer figure.
- If SQL result contains grouped results, summarise the group name and numeric value clearly.
- Do not invent or estimate numbers.
- Do not add outside information.
- Keep the answer short.

User question:
{state.get("question")}

SQL used:
{state.get("sql_query")}

SQL result:
{sql_result_text}

Final answer:
"""

    response = llm.invoke(prompt)

    return {
        **state,
        "final_answer": response.content.strip(),
    }



def fail_node(state: AgentState) -> AgentState:
    return {
        **state,
        "final_answer": (
            f"I could not complete the SQL query after {state.get('max_retries', 3)} retries. "
            f"Last error: {state.get('error')}"
        ),
    }


def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("list_tables", list_tables_node)
    graph.add_node("get_schema", get_schema_node)
    graph.add_node("generate_sql", generate_sql_node)
    graph.add_node("execute_sql", execute_sql_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("fail", fail_node)

    graph.add_edge(START, "list_tables")
    graph.add_edge("list_tables", "get_schema")
    graph.add_edge("get_schema", "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")

    graph.add_conditional_edges(
        "execute_sql",
        route_after_execution,
        {
            "generate_answer": "generate_answer",
            "generate_sql": "generate_sql",
            "fail": "fail"
        }
    )

    graph.add_edge("generate_answer", END)
    graph.add_edge("fail", END)

    return graph.compile()