def calculate_evidence_trust(mode, sql_result=None, rag_similarity=0):
    evidence_scores = []
    reasons = []

    # -----------------------------
    # SQL Evidence Trust
    # -----------------------------
    if mode in ["sql", "both"]:
        if sql_result:
            evidence_scores.append(90)
            reasons.append("SQL returned a valid result.")
        else:
            evidence_scores.append(30)
            reasons.append("SQL result is missing or empty.")

    # -----------------------------
    # RAG Evidence Trust
    # -----------------------------
    if mode in ["rag", "both"]:
        if rag_similarity >= 0.75:
            evidence_scores.append(90)
            reasons.append("RAG evidence has high cosine similarity.")
        elif rag_similarity >= 0.60:
            evidence_scores.append(75)
            reasons.append("RAG evidence has good cosine similarity.")
        elif rag_similarity >= 0.40:
            evidence_scores.append(55)
            reasons.append("RAG evidence has moderate cosine similarity.")
        else:
            evidence_scores.append(25)
            reasons.append("RAG evidence has weak cosine similarity.")

    # -----------------------------
    # No Evidence Case
    # -----------------------------
    if not evidence_scores:
        return {
            "et_score": 30,
            "et_reason": "No reliable evidence source was found.",
        }

    evidence_trust = round(sum(evidence_scores) / len(evidence_scores), 2)

    return {
        "et_score": evidence_trust,
        "et_reason": " ".join(reasons),
    }
