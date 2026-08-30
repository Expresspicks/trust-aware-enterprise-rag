from sentence_transformers import SentenceTransformer
import numpy as np

# Load embedding model once
model = SentenceTransformer("all-MiniLM-L6-v2")


BEHAVIOUR_PATTERNS = [
    # -------------------------
    # Allowed behaviour
    # -------------------------
    {
        "type": "allowed",
        "roles": ["admin_manager"],
        "text": "Admin managers can ask for company-wide sales, finance data, reports, users, and regional comparison data.",
    },
    {
        "type": "allowed",
        "roles": ["manager"],
        "text": "Managers can ask for total sales, regional sales, customer numbers, finance summaries, and report insights.",
    },
    {
        "type": "allowed",
        "roles": ["sales_rep"],
        "text": "Sales representatives can ask for sales, customers, and finance data related only to their assigned region.",
    },
    {
        "type": "allowed",
        "roles": ["admin_manager", "manager", "sales_rep", "intern"],
        "text": "Users can ask for report summaries, risk explanations, and business insights when the information matches their role.",
    },
    # -------------------------
    # Restricted behaviour
    # -------------------------
    {
        "type": "restricted",
        "roles": ["sales_rep"],
        "text": "Sales representatives asking for sales or finance data from another region is restricted behaviour.",
    },
    {
        "type": "restricted",
        "roles": ["sales_rep"],
        "text": "Sales representatives asking for all-region comparison or company-wide regional finance data is restricted behaviour.",
    },
    {
        "type": "restricted",
        "roles": ["intern"],
        "text": "Interns asking for finance table data, sales records, or confidential business data is restricted behaviour.",
    },
    # -------------------------
    # Suspicious behaviour
    # -------------------------
    {
        "type": "suspicious",
        "roles": ["admin_manager", "manager", "sales_rep", "intern"],
        "text": "Users asking for passwords, credentials, login details, or private user information is suspicious behaviour.",
    },
    {
        "type": "suspicious",
        "roles": ["admin_manager", "manager", "sales_rep", "intern"],
        "text": "Users asking to delete, drop, truncate, modify, or damage database tables is suspicious behaviour.",
    },
    {
        "type": "suspicious",
        "roles": ["admin_manager", "manager", "sales_rep", "intern"],
        "text": "Repeated attempts to access denied data or bypass role-based access control is suspicious behaviour.",
    },
]


def get_applicable_patterns(role_name):
    applicable_patterns = []

    for pattern in BEHAVIOUR_PATTERNS:
        if role_name in pattern["roles"]:
            applicable_patterns.append(pattern)

    return applicable_patterns


def calculate_behaviour_trust(
    question,
    role_name=None,
    user_region=None,
    blocked_attempts=0,
    sensitive_attempts=0,
):
    applicable_patterns = get_applicable_patterns(role_name)

    if not applicable_patterns:
        return {
            "bt_score": 0,
            "bt_reason": "No behavioural policy found for this role.",
            "allowed_similarity": 0,
            "restricted_similarity": 0,
            "suspicious_similarity": 0,
            "matched_allowed_pattern": "",
            "matched_restricted_pattern": "",
            "matched_suspicious_pattern": "",
            "best_match_type": "none",
            "best_match_score": 0,
            "session_penalty": 0,
        }

    pattern_texts = [item["text"] for item in applicable_patterns]

    pattern_embeddings = model.encode(
        pattern_texts,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")

    query_text = f"""
    User role: {role_name}
    User region: {user_region}
    User question: {question}
    """

    query_embedding = model.encode(
        [query_text],
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32")

    similarities = np.dot(pattern_embeddings, query_embedding[0])

    best_allowed_score = 0
    best_restricted_score = 0
    best_suspicious_score = 0

    best_allowed_text = ""
    best_restricted_text = ""
    best_suspicious_text = ""

    for i, score in enumerate(similarities):
        pattern_type = applicable_patterns[i]["type"]
        pattern_text = applicable_patterns[i]["text"]
        score = float(score)

        if pattern_type == "allowed" and score > best_allowed_score:
            best_allowed_score = score
            best_allowed_text = pattern_text

        elif pattern_type == "restricted" and score > best_restricted_score:
            best_restricted_score = score
            best_restricted_text = pattern_text

        elif pattern_type == "suspicious" and score > best_suspicious_score:
            best_suspicious_score = score
            best_suspicious_text = pattern_text

    # Select strongest behavioural match
    similarity_scores = {
        "allowed": best_allowed_score,
        "restricted": best_restricted_score,
        "suspicious": best_suspicious_score,
    }

    best_match_type = max(similarity_scores, key=similarity_scores.get)
    best_match_score = similarity_scores[best_match_type]

    # Behaviour Trust formula
    # Allowed behaviour increases BT.
    # Restricted and suspicious behaviour reduce BT.
    bt_score = (
        60
        + (best_allowed_score * 35)
        - (best_restricted_score * 45)
        - (best_suspicious_score * 55)
    )

    # Session behaviour penalty
    session_penalty = (blocked_attempts * 10) + (sensitive_attempts * 5)

    bt_score = bt_score - session_penalty
    bt_score = round(max(0, min(bt_score, 100)), 2)

    if best_match_score < 0.45:
        bt_reason = "No strong behavioural pattern match found."
    elif best_match_type == "allowed":
        bt_reason = "Query is closest to allowed behaviour."
    elif best_match_type == "restricted":
        bt_reason = "Query is closest to restricted behaviour."
    elif best_match_type == "suspicious":
        bt_reason = "Query is closest to suspicious behaviour."
    else:
        bt_reason = "Behavioural trust calculated."

    return {
        "bt_score": bt_score,
        "bt_reason": bt_reason,
        "allowed_similarity": round(best_allowed_score, 3),
        "restricted_similarity": round(best_restricted_score, 3),
        "suspicious_similarity": round(best_suspicious_score, 3),
        "matched_allowed_pattern": best_allowed_text,
        "matched_restricted_pattern": best_restricted_text,
        "matched_suspicious_pattern": best_suspicious_text,
        "best_match_type": best_match_type,
        "best_match_score": round(best_match_score, 3),
        "session_penalty": session_penalty,
    }
