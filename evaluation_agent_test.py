#!/usr/bin/env python3
"""
evaluation_agent_test.py

Reproducible evaluation runner for the Hybrid Trust-Aware RAG prototype.

SOURCE OF TEST CASES
--------------------
The test questions are loaded directly from the Excel workbook sheet:
    Question_Record

The script does NOT hard-code the 40 questions or the paper's final graph values.
It re-runs the recorded questions through the Flask prototype, captures the
current outputs, creates a new evaluation workbook, saves CSV source tables,
and generates evaluation graphs from the re-run results.

IMPORTANT
---------
1. Keep the workbook in the project folder, or pass its path with --workbook.
2. Check USER_CREDENTIALS below and make sure the usernames/passwords match
   the accounts configured in your local prototype.
3. The script follows the order of Question_Record. When the role/profile
   changes, it logs out and logs in as the next test user.
4. Behavioural Trust can therefore retain session effects within a continuous
   block of questions for the same user, which is useful for repeated denied
   or suspicious requests.
"""

import textwrap
import argparse
import os
import time
import traceback
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from app import app


# ============================================================
# SETTINGS
# ============================================================

DEFAULT_WORKBOOK = "trust_aware_sql_rag_evaluation_workbook.xlsx"
QUESTION_SHEET = "Question_Record"

OUTPUT_DIR = Path("evaluation_outputs")
GRAPH_DIR = OUTPUT_DIR / "paper_graphs"
CSV_DIR = OUTPUT_DIR / "graph_source_data"

DELAY_BETWEEN_QUESTIONS_SECONDS = 6

# Flask should raise backend errors during testing so that the runner
# can record them instead of silently continuing.
app.config["TESTING"] = True


# ============================================================
# LOCAL TEST USER CREDENTIALS
# ============================================================
# Verify these three local accounts before running.
# The password is used only by the local Flask test client.
#
# The workbook itself stores role/profile, not passwords.
# If your actual username differs, change only this mapping.

USER_CREDENTIALS = {
    ("admin_manager", "ALL"): {
        "username": "admin_manager",
        "password": os.getenv("EVAL_ADMIN_PASSWORD", ""),
    },
    ("sales_rep", "VIC"): {
        "username": "sales_rep_nsw",
        "password": os.getenv("EVAL_SALES_PASSWORD", ""),
    },
    ("intern", "VIC"): {
        "username": "intern_test",
        "password": os.getenv("EVAL_INTERN_PASSWORD", ""),
    },
}


# ============================================================
# REQUIRED WORKBOOK COLUMNS
# ============================================================

REQUIRED_COLUMNS = [
    "Test_ID",
    "Dataset",
    "Evaluation Area",
    "User Role",
    "Region/Profile",
    "Service Request / Question",
    "Expected Route",
    "Expected Retrieval Focus",
    "Expected Decision",
    "Expected Outcome",
]


# ============================================================
# HELPERS
# ============================================================

def normalise_text(value):
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalise_route(route):
    route = normalise_text(route).lower()
    aliases = {
        "structured retrieval": "sql",
        "sql retrieval": "sql",
        "document retrieval": "rag",
        "rag retrieval": "rag",
        "hybrid retrieval": "both",
        "hybrid sql-rag": "both",
    }
    return aliases.get(route, route or "unknown")


def normalise_decision(value):
    value = normalise_text(value).lower()
    if value in {"allow", "limit", "deny"}:
        return value
    return value or "unknown"


def safe_text(value, limit=1200):
    if value is None:
        return ""
    text = str(value)
    if len(text) > limit:
        return text[:limit] + "...[truncated by evaluation runner]"
    return text


def load_question_record(workbook_path):
    df = pd.read_excel(workbook_path, sheet_name=QUESTION_SHEET)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(
            "Question_Record is missing required columns: "
            + ", ".join(missing)
        )

    # Preserve workbook order because BT/session history may depend on it.
    df = df.copy()
    df["_Workbook_Row_Order"] = range(1, len(df) + 1)

    # Remove completely blank question rows.
    df = df[
        df["Service Request / Question"].notna()
        & (df["Service Request / Question"].astype(str).str.strip() != "")
    ].copy()

    return df


def credential_for(role, profile):
    role = normalise_text(role)
    profile = normalise_text(profile)

    key = (role, profile)
    if key in USER_CREDENTIALS:
        return USER_CREDENTIALS[key]

    # Fallback for a role that has only one configured profile.
    role_matches = [
        value
        for (configured_role, _), value in USER_CREDENTIALS.items()
        if configured_role == role
    ]
    if len(role_matches) == 1:
        return role_matches[0]

    raise KeyError(
        f"No local credential mapping for role={role!r}, profile={profile!r}. "
        "Update USER_CREDENTIALS at the top of evaluation_agent_test.py."
    )


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


def logout(client):
    try:
        client.get("/logout", follow_redirects=True)
    except Exception:
        pass


def clear_chat(client):
    try:
        client.get("/clear_chat", follow_redirects=True)
    except Exception:
        pass


def ask_question(client, question):
    return client.post(
        "/chat",
        data={"question": question},
        follow_redirects=True,
    )


def get_session_snapshot(client):
    with client.session_transaction() as sess:
        return dict(sess)


def get_chat_count(client):
    with client.session_transaction() as sess:
        return len(sess.get("chat_history", []))


def get_latest_chat_if_new(client, previous_count):
    """
    Return the newest chat only if the request created a new chat entry.
    This prevents a failed request from accidentally reusing an older result.
    """
    with client.session_transaction() as sess:
        history = sess.get("chat_history", [])
        if len(history) <= previous_count:
            return None
        return history[-1]


def infer_actual_decision(chat):
    """
    Derive the current decision using the same 0-100 thresholds used
    in the final trust simulation:
        Deny  : TT < 40
        Limit : 40 <= TT < 70
        Allow : TT >= 70

    Hard access blocks override TT.
    """
    access_allowed = chat.get("access_allowed")
    tt = chat.get("trust_score")

    if access_allowed is False:
        return "deny"

    try:
        tt = float(tt)
    except (TypeError, ValueError):
        return "limit"

    if tt < 40:
        return "deny"
    if tt < 70:
        return "limit"
    return "allow"


def decision_comparison(expected, actual):
    """
    Decision-only assessment.

    Pass:
        expected == actual

    Partial Pass:
        output is more cautious than expected, OR an expected Deny
        becomes Limit rather than Allow.

    Fail:
        unsafe/permissive mismatch or another clear mismatch.
    """
    expected = normalise_decision(expected)
    actual = normalise_decision(actual)

    if expected == actual:
        return "Pass"

    if expected == "allow" and actual in {"limit", "deny"}:
        return "Partial Pass"

    if expected == "limit" and actual == "deny":
        return "Partial Pass"

    if expected == "deny" and actual == "limit":
        return "Partial Pass"

    return "Fail"


def automated_result(
    expected_route,
    actual_route,
    expected_decision,
    actual_decision,
    rag_similarity,
):
    """
    Conservative automatic status used for the re-run.

    This deliberately does not pretend to fully judge semantic answer
    correctness. It evaluates route, decision, and weak RAG evidence.

    Manual/canonical answer correctness from the original workbook remains
    available as reference columns in the output workbook.
    """
    route_ok = normalise_route(expected_route) == normalise_route(actual_route)
    decision_result = decision_comparison(expected_decision, actual_decision)

    if decision_result == "Fail":
        return "Fail"

    # Route mismatch cannot be a full pass.
    if not route_ok:
        return "Partial Pass"

    # Weak RAG evidence (<0.40) is treated cautiously for RAG/both routes.
    if normalise_route(actual_route) in {"rag", "both"}:
        try:
            sim = float(rag_similarity)
            if sim > 0 and sim < 0.40:
                return "Partial Pass"
        except (TypeError, ValueError):
            pass

    if decision_result == "Partial Pass":
        return "Partial Pass"

    return "Pass"


def blank_runtime_row(source_row, status, remarks):
    return {
        "Test_ID": source_row["Test_ID"],
        "Dataset": source_row["Dataset"],
        "Evaluation Area": source_row["Evaluation Area"],
        "User Role": source_row["User Role"],
        "Region/Profile": source_row["Region/Profile"],
        "Service Request / Question": source_row["Service Request / Question"],
        "Expected Route": normalise_route(source_row["Expected Route"]),
        "Actual Route": status,
        "Route Match": "No",
        "Expected Decision": normalise_decision(source_row["Expected Decision"]).title(),
        "Actual Decision": status,
        "Access Allowed": "",
        "CT": "",
        "BT": "",
        "ET": "",
        "TT": "",
        "RAG Similarity": "",
        "Generated SQL": "",
        "SQL Result Summary": "",
        "Final Answer / Output Summary": "",
        "CT Reason": "",
        "BT Reason": "",
        "ET Reason": "",
        "Router Reason": "",
        "Automated Result": "Not Completed",
        "Reference Answer Correct?": source_row.get("Answer Correct?", ""),
        "Reference Result Status": source_row.get("Result Status", ""),
        "Matches Reference Status": "No",
        "Expected Retrieval Focus": source_row.get("Expected Retrieval Focus", ""),
        "Expected Outcome": source_row.get("Expected Outcome", ""),
        "Reviewer Notes": source_row.get("Reviewer Notes", ""),
        "Runtime Remarks": remarks,
    }


# ============================================================
# EVALUATION RUNNER
# ============================================================

def run_evaluation(question_df):
    runtime_rows = []

    current_identity = None

    with app.test_client() as client:
        for _, source in question_df.iterrows():
            test_id = normalise_text(source["Test_ID"])
            role = normalise_text(source["User Role"])
            profile = normalise_text(source["Region/Profile"])
            question = normalise_text(source["Service Request / Question"])

            identity = (role, profile)

            # Login only when the workbook changes user/profile.
            # This preserves session history within each continuous user block.
            if identity != current_identity:
                if current_identity is not None:
                    logout(client)

                credential = credential_for(role, profile)

                print("\n" + "=" * 84)
                print(f"Switching test user -> role={role}, profile={profile}")
                print(f"Local username      -> {credential['username']}")
                print("=" * 84)

                try:
                    login(
                        client,
                        credential["username"],
                        credential["password"],
                    )
                    snapshot = get_session_snapshot(client)
                except Exception as exc:
                    snapshot = {}
                    print(f"Login error: {exc}")

                if "user_id" not in snapshot:
                    runtime_rows.append(
                        blank_runtime_row(
                            source,
                            "LOGIN_FAILED",
                            (
                                f"Login failed for role={role}, profile={profile}. "
                                "Check USER_CREDENTIALS."
                            ),
                        )
                    )
                    current_identity = identity
                    continue

                clear_chat(client)
                current_identity = identity

            print(f"Running {test_id}: {question}")

            expected_route = normalise_route(source["Expected Route"])
            expected_decision = normalise_decision(source["Expected Decision"])

            previous_count = get_chat_count(client)

            try:
                response = ask_question(client, question)
                time.sleep(DELAY_BETWEEN_QUESTIONS_SECONDS)

                if response.status_code >= 400:
                    runtime_rows.append(
                        blank_runtime_row(
                            source,
                            f"HTTP_{response.status_code}",
                            f"/chat returned HTTP {response.status_code}.",
                        )
                    )
                    continue

                chat = get_latest_chat_if_new(client, previous_count)

            except Exception as exc:
                runtime_rows.append(
                    blank_runtime_row(
                        source,
                        "ERROR",
                        (
                            f"Runtime error: {exc} | "
                            f"{traceback.format_exc(limit=2)}"
                        ),
                    )
                )
                continue

            if chat is None:
                runtime_rows.append(
                    blank_runtime_row(
                        source,
                        "NO_CHAT",
                        "No new chat entry was created by the request.",
                    )
                )
                continue

            actual_route = normalise_route(chat.get("mode"))
            actual_decision = infer_actual_decision(chat)
            rag_similarity = chat.get("rag_similarity")

            auto_result = automated_result(
                expected_route=expected_route,
                actual_route=actual_route,
                expected_decision=expected_decision,
                actual_decision=actual_decision,
                rag_similarity=rag_similarity,
            )

            reference_status = normalise_text(source.get("Result Status", ""))

            runtime_rows.append(
                {
                    "Test_ID": test_id,
                    "Dataset": source["Dataset"],
                    "Evaluation Area": source["Evaluation Area"],
                    "User Role": role,
                    "Region/Profile": profile,
                    "Service Request / Question": question,
                    "Expected Route": expected_route,
                    "Actual Route": actual_route,
                    "Route Match": "Yes" if actual_route == expected_route else "No",
                    "Expected Decision": expected_decision.title(),
                    "Actual Decision": actual_decision.title(),
                    "Access Allowed": chat.get("access_allowed"),
                    "CT": chat.get("contextual_trust"),
                    "BT": chat.get("behavioural_trust"),
                    "ET": chat.get("evidence_trust"),
                    "TT": chat.get("trust_score"),
                    "RAG Similarity": rag_similarity,
                    "Generated SQL": safe_text(chat.get("sql_query"), 1500),
                    "SQL Result Summary": safe_text(chat.get("sql_result"), 1500),
                    "Final Answer / Output Summary": safe_text(chat.get("answer"), 1500),
                    "CT Reason": safe_text(chat.get("ct_reason"), 800),
                    "BT Reason": safe_text(chat.get("bt_reason"), 800),
                    "ET Reason": safe_text(chat.get("et_reason"), 800),
                    "Router Reason": safe_text(chat.get("router_reason"), 800),
                    "Automated Result": auto_result,
                    "Reference Answer Correct?": source.get("Answer Correct?", ""),
                    "Reference Result Status": reference_status,
                    "Matches Reference Status": (
                        "Yes" if auto_result == reference_status else "No"
                    ),
                    "Expected Retrieval Focus": source.get("Expected Retrieval Focus", ""),
                    "Expected Outcome": source.get("Expected Outcome", ""),
                    "Reviewer Notes": source.get("Reviewer Notes", ""),
                    "Runtime Remarks": "",
                }
            )

        logout(client)

    return pd.DataFrame(runtime_rows)


# ============================================================
# SUMMARY TABLES
# ============================================================

PAPER_CATEGORY_ORDER = [
    "SQL Retrieval",
    "RAG Retrieval",
    "Hybrid SQL-RAG",
    "Access Control",
    "Safety",
    "External Dataset SQL",
    "Access-Governance Reasoning",
]


def build_functional_summary(results_df):
    completed = results_df[
        results_df["Automated Result"].isin(["Pass", "Partial Pass", "Fail"])
    ].copy()

    summary = (
        completed.groupby(["Evaluation Area", "Automated Result"])
        .size()
        .unstack(fill_value=0)
    )

    for column in ["Pass", "Partial Pass", "Fail"]:
        if column not in summary.columns:
            summary[column] = 0

    summary["Total"] = summary[["Pass", "Partial Pass", "Fail"]].sum(axis=1)
    summary["Pass Rate (%)"] = (
        summary["Pass"] / summary["Total"].replace(0, pd.NA) * 100
    ).fillna(0)

    summary = summary.reset_index()

    order_lookup = {name: i for i, name in enumerate(PAPER_CATEGORY_ORDER)}
    summary["_order"] = summary["Evaluation Area"].map(
        lambda x: order_lookup.get(x, 999)
    )
    summary = summary.sort_values(["_order", "Evaluation Area"]).drop(
        columns="_order"
    )

    return summary


def build_route_summary(results_df):
    completed = results_df[
        results_df["Route Match"].isin(["Yes", "No"])
    ].copy()

    grouped = (
        completed.groupby("Evaluation Area")
        .agg(
            Total=("Test_ID", "count"),
            Route_Matches=("Route Match", lambda s: (s == "Yes").sum()),
        )
        .reset_index()
    )
    grouped["Route Accuracy (%)"] = (
        grouped["Route_Matches"] / grouped["Total"] * 100
    )
    return grouped


def build_decision_matrix(results_df):
    completed = results_df[
        results_df["Actual Decision"].isin(["Allow", "Limit", "Deny"])
    ].copy()

    matrix = pd.crosstab(
        completed["Expected Decision"],
        completed["Actual Decision"],
    )

    order = ["Allow", "Limit", "Deny"]
    matrix = matrix.reindex(index=order, columns=order, fill_value=0)
    return matrix


def build_trust_by_role(results_df):
    numeric = results_df.copy()
    for column in ["CT", "BT", "ET", "TT"]:
        numeric[column] = pd.to_numeric(numeric[column], errors="coerce")

    return (
        numeric.groupby(["User Role", "Region/Profile"])[["CT", "BT", "ET", "TT"]]
        .mean()
        .round(2)
        .reset_index()
    )


def build_rag_evidence_summary(results_df):
    rag = results_df[
        results_df["Expected Route"].isin(["rag", "both"])
    ].copy()

    rag["RAG Similarity"] = pd.to_numeric(
        rag["RAG Similarity"], errors="coerce"
    )

    return (
        rag.groupby("Evaluation Area")
        .agg(
            Questions=("Test_ID", "count"),
            Average_RAG_Similarity=("RAG Similarity", "mean"),
        )
        .reset_index()
        .round({"Average_RAG_Similarity": 3})
    )


# ============================================================
# GRAPH GENERATION
# ============================================================

def save_graph_source(df, filename):
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    path = CSV_DIR / filename
    df.to_csv(path, index=False)
    return path


def plot_functional_evaluation(summary):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    categories = summary["Evaluation Area"].tolist()
    total = summary["Total"].tolist()
    passed = summary["Pass"].tolist()
    partial = summary["Partial Pass"].tolist()
    failed = summary["Fail"].tolist()
    pass_rate = summary["Pass Rate (%)"].tolist()

    x = list(range(len(categories)))
    width = 0.20

    fig, ax1 = plt.subplots(figsize=(15, 8))

    ax1.bar([v - 1.5 * width for v in x], total, width, label="Total")
    ax1.bar([v - 0.5 * width for v in x], passed, width, label="Pass")
    ax1.bar([v + 0.5 * width for v in x], partial, width, label="Partial Pass")
    ax1.bar([v + 1.5 * width for v in x], failed, width, label="Fail")

    ax1.set_title("Functional Evaluation Results by Test Category", fontsize=18, fontweight="bold")
    ax1.set_ylabel("Number of test cases", fontsize=12)
    ax1.set_xlabel("Test categories", fontsize=12)
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories, rotation=0, ha="center")
    ax1.grid(axis="y", alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(x, pass_rate, linewidth=2.5, label="Pass Rate")
    ax2.set_ylabel("Pass rate (%)", fontsize=12)
    ax2.set_ylim(0, 120)

    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(
        handles1 + handles2,
        labels1 + labels2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=5,
        frameon=False,
    )

    fig.tight_layout()
    path = GRAPH_DIR / "functional_evaluation_results_by_test_category.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_route_accuracy(route_summary):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.bar(
        route_summary["Evaluation Area"],
        route_summary["Route Accuracy (%)"],
    )
    ax.set_title("Route Accuracy by Test Category", fontsize=18, fontweight="bold")
    ax.set_ylabel("Route accuracy (%)")
    ax.set_xlabel("Test categories")
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    plt.xticks(rotation=25, ha="right")

    fig.tight_layout()
    path = GRAPH_DIR / "route_accuracy_by_test_category.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_decision_matrix(matrix):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    labels = ["Allow", "Limit", "Deny"]
    values = matrix.loc[labels, labels].to_numpy()

    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    image = ax.imshow(values, cmap="Greens")

    ax.set_xticks(range(3))
    ax.set_yticks(range(3))
    ax.set_xticklabels(labels)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Actual Decision")
    ax.set_ylabel("Expected Decision")
    ax.set_title("Expected vs Actual Decision", fontsize=16, fontweight="bold")

    threshold = values.max() / 2 if values.max() else 0
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            ax.text(
                j,
                i,
                str(values[i, j]),
                ha="center",
                va="center",
                color="white" if values[i, j] > threshold else "black",
                fontsize=12,
            )

    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()

    path = GRAPH_DIR / "functional_expected_vs_actual_decision.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def plot_trust_by_role(trust_summary):
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)

    labels = (
        trust_summary["User Role"].astype(str)
        + " / "
        + trust_summary["Region/Profile"].astype(str)
    ).tolist()

    x = list(range(len(labels)))
    width = 0.2

    fig, ax = plt.subplots(figsize=(10, 7))
    for idx, metric in enumerate(["CT", "BT", "ET", "TT"]):
        offsets = [v + (idx - 1.5) * width for v in x]
        ax.bar(offsets, trust_summary[metric], width, label=metric)

    ax.set_title("Average Trust Scores by User Role", fontsize=17, fontweight="bold")
    ax.set_ylabel("Average trust score (0-100)")
    ax.set_xlabel("User role / profile")
    ax.set_ylim(0, 105)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(ncol=4)

    fig.tight_layout()
    path = GRAPH_DIR / "average_trust_scores_by_user_role.png"
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return path


def generate_graphs(results_df):
    functional = build_functional_summary(results_df)
    route = build_route_summary(results_df)
    matrix = build_decision_matrix(results_df)
    trust = build_trust_by_role(results_df)
    rag = build_rag_evidence_summary(results_df)

    save_graph_source(
        functional,
        "functional_evaluation_by_category.csv",
    )
    save_graph_source(
        route,
        "route_accuracy_by_category.csv",
    )
    save_graph_source(
        matrix.reset_index().rename(columns={"Expected Decision": "Expected"}),
        "functional_decision_matrix.csv",
    )
    save_graph_source(
        trust,
        "average_trust_scores_by_role.csv",
    )
    save_graph_source(
        rag,
        "rag_evidence_summary.csv",
    )

    graph_paths = [
        plot_functional_evaluation(functional),
        plot_route_accuracy(route),
        plot_decision_matrix(matrix),
        plot_trust_by_role(trust),
    ]

    return {
        "functional_summary": functional,
        "route_summary": route,
        "decision_matrix": matrix,
        "trust_summary": trust,
        "rag_summary": rag,
        "graph_paths": graph_paths,
    }


# ============================================================
# OUTPUT WORKBOOK
# ============================================================

def export_results(results_df, summaries):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"evaluation_rerun_{timestamp}.xlsx"

    overall = (
        results_df["Automated Result"]
        .value_counts()
        .reindex(["Pass", "Partial Pass", "Fail", "Not Completed"], fill_value=0)
        .rename_axis("Result")
        .reset_index(name="Count")
    )

    reference_comparison = (
        results_df["Matches Reference Status"]
        .value_counts()
        .rename_axis("Matches Reference Status")
        .reset_index(name="Count")
    )

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        results_df.to_excel(
            writer,
            sheet_name="Re-run Results",
            index=False,
        )
        overall.to_excel(
            writer,
            sheet_name="Overall Summary",
            index=False,
        )
        summaries["functional_summary"].to_excel(
            writer,
            sheet_name="Functional Summary",
            index=False,
        )
        summaries["route_summary"].to_excel(
            writer,
            sheet_name="Route Summary",
            index=False,
        )
        summaries["decision_matrix"].to_excel(
            writer,
            sheet_name="Decision Matrix",
        )
        summaries["trust_summary"].to_excel(
            writer,
            sheet_name="Trust by Role",
            index=False,
        )
        summaries["rag_summary"].to_excel(
            writer,
            sheet_name="RAG Evidence",
            index=False,
        )
        reference_comparison.to_excel(
            writer,
            sheet_name="Reference Comparison",
            index=False,
        )

    return output_file


# ============================================================
# REFERENCE-ONLY GRAPH MODE
# ============================================================

def reference_summary_from_workbook(question_df):
    """
    Build graph data from the already-recorded Question_Record values
    without calling the Flask application.

    This is useful for reproducing figures from the canonical 40-case
    evidence table exactly as it currently exists.
    """
    reference = question_df.copy()

    reference = reference.rename(
        columns={
            "Result Status": "Automated Result",
            "Actual Route": "Actual Route",
            "CT": "CT",
            "BT": "BT",
            "ET": "ET",
            "TT": "TT",
            "RAG Similarity": "RAG Similarity",
        }
    )

    reference["Route Match"] = reference.apply(
        lambda r: (
            "Yes"
            if normalise_route(r["Expected Route"])
            == normalise_route(r["Actual Route"])
            else "No"
        ),
        axis=1,
    )

    return reference


# ============================================================
# MAIN
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run the 40-question enterprise RAG evaluation from "
            "Question_Record and generate reproducible graph outputs."
        )
    )
    parser.add_argument(
        "--workbook",
        default=DEFAULT_WORKBOOK,
        help="Path to the evaluation workbook.",
    )
    parser.add_argument(
        "--reference-graphs-only",
        action="store_true",
        help=(
            "Do not call the LLM/application. Generate graphs directly "
            "from the recorded Question_Record results."
        ),
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_BETWEEN_QUESTIONS_SECONDS,
        help="Delay between live questions in seconds.",
    )
    return parser.parse_args()


def main():
    global DELAY_BETWEEN_QUESTIONS_SECONDS

    args = parse_args()
    DELAY_BETWEEN_QUESTIONS_SECONDS = args.delay

    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        raise FileNotFoundError(
            f"Workbook not found: {workbook_path}\n"
            "Use --workbook /full/path/to/file.xlsx"
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    CSV_DIR.mkdir(parents=True, exist_ok=True)

    question_df = load_question_record(workbook_path)

    print("=" * 84)
    print(f"Workbook: {workbook_path}")
    print(f"Sheet:    {QUESTION_SHEET}")
    print(f"Cases:    {len(question_df)}")
    print("=" * 84)

    if args.reference_graphs_only:
        results_df = reference_summary_from_workbook(question_df)
        summaries = generate_graphs(results_df)

        print("\nReference graphs generated from Question_Record.")
        for path in summaries["graph_paths"]:
            print(f"  {path}")
        return

    results_df = run_evaluation(question_df)

    summaries = generate_graphs(results_df)
    output_file = export_results(results_df, summaries)

    print("\n" + "=" * 84)
    print("Evaluation completed.")
    print(f"Re-run workbook: {output_file}")
    print(f"Graph folder:    {GRAPH_DIR}")
    print(f"CSV source data: {CSV_DIR}")
    print("=" * 84)

    print("\nGraphs:")
    for path in summaries["graph_paths"]:
        print(f"  {path}")


if __name__ == "__main__":
    main()
