from flask import Flask, request, redirect, session, url_for, render_template
import os
from sql_agent_graph import build_agent, get_llm
from query_router import route_question_llm
from routes import register_routes
from rag_service import get_rag_context
from trust.bt import calculate_behaviour_trust
from trust.ct import calculate_contextual_trust
from trust.et import calculate_evidence_trust

app = Flask(__name__)
app.secret_key = ""

agent = build_agent()

register_routes(app, agent)


##HYBRID ANSWER##
def generate_hybrid_answer(
    question, sql_answer=None, sql_result=None, rag_context=None
):
    llm = get_llm()

    prompt = f"""
You are a finance AI assistant.

Available evidence:

SQL answer:
{sql_answer if sql_answer else "Not used"}

SQL result:
{sql_result if sql_result else "Not used"}

PDF knowledge context:
{rag_context if rag_context else "Not used"}

Rules:
- Use only the available evidence above.
- If SQL evidence is available, include the exact numeric value from SQL.
- If document/RAG context is available, use it for explanation, risks, reasons, or insights.
- Do not invent missing information.
- If the answer is not available in the evidence, say it is not available.
- Keep the answer clear and short.
- Do not use **bold** formatting.
- Return plain text only.

User question:
{question}

Final answer:
"""

    response = llm.invoke(prompt)
    return response.content.strip()


def contains_sensitive_terms(question):
    sensitive_words = [
        "password",
        "credentials",
        "all users",
        "delete",
        "drop",
        "truncate",
        "private",
        "confidential",
    ]

    q = question.lower()
    return any(word in q for word in sensitive_words)


############# ROLE-AWARE CONTEXT ########################
def apply_access_control(
    question, mode, sql_query=None, sql_result=None, final_answer=None, rag_similarity=0
):
    if contains_sensitive_terms(question):
        session["sensitive_attempts"] = session.get("sensitive_attempts", 0) + 1

    ct = calculate_contextual_trust(
        question=question,
        mode=mode,
        sql_query=sql_query,
        role_name=session.get("role_name"),
        user_region=session.get("region"),
    )
    bt = calculate_behaviour_trust(
        question=question,
        role_name=session.get("role_name"),
        user_region=session.get("region"),
        blocked_attempts=session.get("blocked_attempts", 0),
        sensitive_attempts=session.get("sensitive_attempts", 0),
    )
    et = calculate_evidence_trust(
        mode=mode, sql_result=sql_result, rag_similarity=rag_similarity
    )

    # Weighted trust formula: TT = w1CT + w2BT + w3ET
    # These prototype weights can later be tuned by context/simulation.
    w1, w2, w3 = 0.4, 0.3, 0.3

    total_trust = round(
        (w1 * ct["ct_score"]) + (w2 * bt["bt_score"]) + (w3 * et["et_score"]),
        2,
    )

    decision = {
        "allowed": True,
        "answer": final_answer,
        "trust_score": total_trust,
        "contextual_trust": ct["ct_score"],
        "behavioural_trust": bt["bt_score"],
        "evidence_trust": et["et_score"],
        "ct_reason": ct["ct_reason"],
        "bt_reason": bt["bt_reason"],
        "et_reason": et["et_reason"],
        "allowed_similarity": bt.get("allowed_similarity"),
        "restricted_similarity": bt.get("restricted_similarity"),
        "suspicious_similarity": bt.get("suspicious_similarity"),
        "matched_allowed_pattern": bt.get("matched_allowed_pattern"),
        "matched_restricted_pattern": bt.get("matched_restricted_pattern"),
        "matched_suspicious_pattern": bt.get("matched_suspicious_pattern"),
        "reason": "Access allowed",
    }

    # Hard contextual block
    if ct["hard_block"]:
        session["blocked_attempts"] = session.get("blocked_attempts", 0) + 1
        decision["allowed"] = False
        decision["answer"] = ct["block_message"]
        decision["reason"] = ct["ct_reason"]
        return decision
    # 2. Low contextual trust block
    if ct["ct_score"] < 40:
        session["blocked_attempts"] = session.get("blocked_attempts", 0) + 1

        decision["allowed"] = False
        decision["answer"] = "Access denied due to low contextual trust."
        decision["reason"] = ct["ct_reason"]

        return decision

    # 3. If no block, return allowed decision

    # Total trust threshold
    if total_trust < 40:
        session["blocked_attempts"] = session.get("blocked_attempts", 0) + 1

        decision["allowed"] = False
        decision["answer"] = "Access denied due to low total trust score."
        decision["reason"] = "Total trust score is below minimum threshold."

    elif total_trust < 60:
        decision["allowed"] = True
        decision["reason"] = "Limited trust. Response should be treated cautiously."

    elif total_trust < 80:
        decision["allowed"] = True
        decision["reason"] = "Moderate trust. Response allowed."

    else:
        decision["allowed"] = True
        decision["reason"] = "High trust. Full response allowed."

    return decision


##########################################################################


###CHAT AREA###
@app.route("/chat", methods=["POST"])
def chat():
    if "user_id" not in session:
        return redirect(url_for("login"))

    question = request.form.get("question","").strip()
    session["total_questions"] = session.get("total_questions", 0) + 1
    chat_history = session.get("chat_history", [])

    # ---------------- QUERY ROUTING ----------------
    router_result = route_question_llm(question)

    mode = (router_result.get("route") or "both").lower()
    router_reason = router_result.get("reason") or "No router reason returned."

    # Important:
    # Router decides route only. SQL agent receives the original question.
    # This avoids bad router-generated SQL-like tasks.
    sql_task = question
    rag_task = router_result.get("rag_task") or question

    # ---------------- SAFETY ROUTE ----------------
    # Unsafe/sensitive questions are blocked before SQL or RAG execution.
    if mode == "safety":
        final_answer = (
            "Access denied. This request contains unsafe or sensitive intent."
        )

        session["sensitive_attempts"] = session.get("sensitive_attempts", 0) + 1

        chat_history.append(
            {
                "question": question,
                "answer": final_answer,
                "mode": "safety",
                "router_reason": router_reason,
                "sql_task": "",
                "rag_task": "",
                "sql_query": None,
                "sql_result": None,
                "rag_context": None,
                "rag_similarity": 0,
                "trust_score": 0,
                "contextual_trust": 0,
                "behavioural_trust": 0,
                "evidence_trust": 0,
                "ct_reason": "Blocked by safety router.",
                "bt_reason": "Unsafe or sensitive query intent detected.",
                "et_reason": "No evidence retrieval performed because request was blocked.",
                "allowed_similarity": None,
                "restricted_similarity": None,
                "suspicious_similarity": None,
                "matched_allowed_pattern": None,
                "matched_restricted_pattern": None,
                "matched_suspicious_pattern": None,
                "blocked_attempts": session.get("blocked_attempts", 0),
                "sensitive_attempts": session.get("sensitive_attempts", 0),
                "total_questions": session.get("total_questions", 0),
                "access_allowed": False,
                "access_reason": "Blocked before retrieval because unsafe or sensitive intent was detected.",
                "role_name": session.get("role_name"),
                "region": session.get("region"),
            }
        )

        session["chat_history"] = chat_history

        return render_template("dashboard.html", chat_history=chat_history)

    # ---------------- DEFAULT VALUES ----------------
    sql_query = None
    sql_result = None
    sql_answer = None
    rag_context = None
    rag_similarity = 0

    # ---------------- SQL STATE ----------------
    initial_state = {
        "question": sql_task,
        "user_id": session.get("user_id"),
        "role": session.get("role_name"),
        "region": session.get("region"),
        "tables": None,
        "schema": None,
        "sql_query": None,
        "sql_result": None,
        "error": None,
        "retries": 0,
        "max_retries": 3,
        "final_answer": None,
    }

    # ---------------- RUN SQL IF NEEDED ----------------
    if mode in ["sql", "both"]:
        result = agent.invoke(initial_state)
        sql_query = result.get("sql_query")
        sql_result = result.get("sql_result")
        sql_answer = result.get("final_answer")

    # ---------------- RUN RAG IF NEEDED ----------------
    if mode in ["rag", "both"]:
        rag_data = get_rag_context(rag_task)
        rag_context = rag_data["context"]
        rag_similarity = rag_data["average_similarity"]

    # ---------------- TRUST DECISION ----------------
    decision = apply_access_control(
        question=question,
        mode=mode,
        sql_query=sql_query,
        sql_result=sql_result,
        final_answer=sql_answer,
        rag_similarity=rag_similarity,
    )

    # ---------------- FINAL ANSWER GENERATION ----------------
    if not decision["allowed"]:
        final_answer = decision["answer"]

    elif mode == "sql":
        final_answer = sql_answer

    elif mode == "rag":
        final_answer = generate_hybrid_answer(
            question=question,
            sql_answer=None,
            sql_result=None,
            rag_context=rag_context,
        )

    else:
        final_answer = generate_hybrid_answer(
            question=question,
            sql_answer=sql_answer,
            sql_result=sql_result,
            rag_context=rag_context,
        )

    # ---------------- TERMINAL DEBUG OUTPUT ----------------
    print("\n==============================")
    print("USER QUESTION:")
    print(question)

    print("\nROUTE MODE:")
    print(mode)

    print("\nROUTER REASON:")
    print(router_reason)

    print("\nSQL TASK:")
    print(sql_task)

    print("\nRAG TASK:")
    print(rag_task)

    print("\nUSER ROLE:")
    print(session.get("role_name"))

    print("\nUSER REGION:")
    print(session.get("region"))

    print("\nGENERATED SQL:")
    print(sql_query)

    print("\nSQL RESULT:")
    print(sql_result)

    print("\nRAG CONTEXT:")
    print(rag_context)

    print("\nRAG SIMILARITY:")
    print(rag_similarity)

    print("\nCONTEXTUAL TRUST:")
    print(decision.get("contextual_trust"))

    print("\nBEHAVIOURAL TRUST:")
    print(decision.get("behavioural_trust"))

    print("\nEVIDENCE TRUST:")
    print(decision.get("evidence_trust"))

    print("\nTOTAL TRUST:")
    print(decision.get("trust_score"))

    print("\nACCESS ALLOWED:")
    print(decision.get("allowed"))

    print("\nACCESS REASON:")
    print(decision.get("reason"))

    print("\nFINAL ANSWER:")
    print(final_answer)
    print("==============================\n")

    # ---------------- SAVE CHAT HISTORY ----------------
    chat_history.append(
        {
            "question": question,
            "answer": final_answer,
            "mode": mode,
            "router_reason": router_reason,
            "sql_task": sql_task,
            "rag_task": rag_task,
            "sql_query": sql_query,
            "sql_result": sql_result,
            "rag_context": rag_context,
            "rag_similarity": rag_similarity,
            "trust_score": decision["trust_score"],
            "contextual_trust": decision.get("contextual_trust"),
            "behavioural_trust": decision.get("behavioural_trust"),
            "evidence_trust": decision.get("evidence_trust"),
            "ct_reason": decision.get("ct_reason"),
            "bt_reason": decision.get("bt_reason"),
            "et_reason": decision.get("et_reason"),
            "allowed_similarity": decision.get("allowed_similarity"),
            "restricted_similarity": decision.get("restricted_similarity"),
            "suspicious_similarity": decision.get("suspicious_similarity"),
            "matched_allowed_pattern": decision.get("matched_allowed_pattern"),
            "matched_restricted_pattern": decision.get("matched_restricted_pattern"),
            "matched_suspicious_pattern": decision.get("matched_suspicious_pattern"),
            "blocked_attempts": session.get("blocked_attempts", 0),
            "sensitive_attempts": session.get("sensitive_attempts", 0),
            "total_questions": session.get("total_questions", 0),
            "access_allowed": decision["allowed"],
            "access_reason": decision.get("reason"),
            "role_name": session.get("role_name"),
            "region": session.get("region"),
        }
    )

    session["chat_history"] = chat_history

    return render_template("dashboard.html", chat_history=chat_history)


if __name__ == "__main__":
    app.run(debug=True)
