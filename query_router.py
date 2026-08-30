import json
import re
from sql_tools import list_tables, get_table_schema
from sql_agent_graph import get_llm

DOCUMENT_SUMMARY = """
The PDF report contains regional financial insights for NSW, VIC, and QLD.
It includes regional performance, sales strength, customer behaviour,
risk indicators, business recommendations, market dependency, volatility,
seasonal demand, and comparative analysis.
"""


UNSAFE_TERMS = [
    "delete",
    "drop",
    "alter",
    "update",
    "truncate",
    "create",
    "revoke",
    "grant",
    "password",
    "credentials",
    "login details",
    "private user information",
]


def is_unsafe_question(question):
    q = question.lower()
    for term in UNSAFE_TERMS:
        if term in q:
            return True, term

    return False, None


def extract_json_from_response(content):
    content = content.strip()
    try:
        return json.loads(content)
    except Exception:
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)

    if match:
        return json.loads(match.group())
    raise ValueError("No valid JSON found in the outer response.")


def get_schema_summary():
    tables = list_tables()
    schema_parts = []

    for table in tables:
        schema = get_table_schema(table)
        schema_parts.append(f"Table: {table}\nSchema: {schema}")

    return "\n\n".join(schema_parts)


def route_question_llm(question):
    unsafe, matched_term = is_unsafe_question(question)
    if unsafe:
        return {
            "route": "safety",
            "reason": f"Unsafe or sensitive intent detected:{matched_term}",
            "sql_task": "",
            "rag_task": "",
        }

    llm = get_llm()
    schema_summary = get_schema_summary()

    prompt = f"""
You are an intelligent query router for a hybrid enterprise AI system.

Your task is to classify the user question into exactly one route:
sql, rag, or both.

ROUTING RULES:

1. Use "sql" only when the question needs structured database calculation or values.
Examples:
- total sales
- average sales
- highest sales
- lowest sales
- customer count
- figures
- month/year/region filtering
- finance table values
- numeric comparison from database

2. Use "rag" only when the question asks about report/document knowledge.
Examples:
- according to the report
- what does the report say
- risk
- recommendations
- reasons
- explanations
- insights
- market dependency
- metropolitan markets
- volatility
- seasonal demand
- customer behaviour from the report
- exact phrase from document

3. Use "both" only when the question clearly needs BOTH:
- a database number/calculation AND
- a report/document explanation.

Important:
- Do not choose "both" just because the question contains a region name.
- Region names such as NSW, VIC, and QLD can appear in SQL or RAG questions.
- If the question asks "according to the report" and does not ask for numeric database calculation, choose "rag".
- If the question asks for sales/customer numbers and does not ask for report explanation, choose "sql".
- If unsure between rag and both, choose rag unless a clear database calculation is required.

Database schema:
{schema_summary}

Document knowledge summary:
{DOCUMENT_SUMMARY}

User question:
{question}

Return ONLY valid JSON in this exact format:
{{
    "route": "sql" or "rag" or "both",
    "reason": "short reason",
    "sql_task": "only the SQL/database part of the question, or empty string",
    "rag_task": "only the report/document part of the question, or empty string"
}}
"""
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()

        data = extract_json_from_response(content)

        route = data.get("route", "both").lower().strip()

        if route not in ["sql", "rag", "both"]:
            route = "both"

        sql_task = data.get("sql_task", "").strip()
        rag_task = data.get("rag_task", "").strip()

        if route == "sql" and not sql_task:
            sql_task = question

        if route == "rag" and not rag_task:
            rag_task = question

        if route == "both":
            if not sql_task:
                sql_task = question
            if not rag_task:
                rag_task = question

        return {
            "route": route,
            "reason": data.get("reason", "LLM routing completed."),
            "sql_task": sql_task,
            "rag_task": rag_task,
        }

    except Exception as e:
        return {
            "route": "both",
            "reason": f"Router failed, defaulted to both. Error: {str(e)}",
            "sql_task": question,
            "rag_task": question,
        }
