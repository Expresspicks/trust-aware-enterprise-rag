import os
import random
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# SETTINGS
# ============================================================

SEED = 42
N_SAMPLES = 500

W_CT = 0.4
W_BT = 0.3
W_ET = 0.3

OUTPUT_DIR = "trust_simulation_graphs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# SYNTHETIC SCENARIO GENERATOR
# ============================================================

def generate_synthetic_samples(n=500, seed=42):
    """
    Generate one reproducible canonical set of synthetic scenarios.
    """

    rng = random.Random(seed)

    samples = []

    scenario_types = [
        "admin_normal",
        "manager_normal",
        "sales_rep_own_region",
        "sales_rep_other_region",
        "intern_finance",
        "sensitive_query",
        "weak_evidence",
        "suspicious_behaviour",
        "rag_strong_evidence",
        "rag_weak_evidence",
    ]

    for _ in range(n):

        scenario = rng.choice(scenario_types)

        if scenario == "admin_normal":
            ct = rng.randint(90, 100)
            bt = rng.randint(85, 100)
            et = rng.randint(80, 100)
            expected = "allow"

        elif scenario == "manager_normal":
            ct = rng.randint(80, 90)
            bt = rng.randint(80, 100)
            et = rng.randint(75, 95)
            expected = "allow"

        elif scenario == "sales_rep_own_region":
            ct = rng.randint(70, 80)
            bt = rng.randint(75, 100)
            et = rng.randint(75, 95)
            expected = "allow"

        elif scenario == "sales_rep_other_region":
            ct = rng.randint(15, 35)
            bt = rng.randint(60, 95)
            et = rng.randint(70, 95)
            expected = "deny"

        elif scenario == "intern_finance":
            ct = rng.randint(10, 30)
            bt = rng.randint(60, 90)
            et = rng.randint(70, 95)
            expected = "deny"

        elif scenario == "sensitive_query":
            ct = rng.randint(5, 25)
            bt = rng.randint(20, 60)
            et = rng.randint(20, 70)
            expected = "deny"

        elif scenario == "weak_evidence":
            ct = rng.randint(60, 90)
            bt = rng.randint(70, 100)
            et = rng.randint(10, 40)
            expected = "limit"

        elif scenario == "suspicious_behaviour":
            ct = rng.randint(50, 80)
            bt = rng.randint(10, 40)
            et = rng.randint(60, 90)
            expected = "limit"

        elif scenario == "rag_strong_evidence":
            ct = rng.randint(70, 90)
            bt = rng.randint(75, 100)
            et = rng.randint(80, 100)
            expected = "allow"

        elif scenario == "rag_weak_evidence":
            ct = rng.randint(60, 85)
            bt = rng.randint(70, 100)
            et = rng.randint(15, 45)
            expected = "limit"

        samples.append(
            {
                "scenario": scenario,
                "CT": ct,
                "BT": bt,
                "ET": et,
                "expected": expected,
            }
        )

    return samples


# ============================================================
# TRUST FORMULA
# ============================================================

def calculate_total_trust(
    ct,
    bt,
    et,
    w_ct=W_CT,
    w_bt=W_BT,
    w_et=W_ET
):
    return round(
        (w_ct * ct)
        + (w_bt * bt)
        + (w_et * et),
        2
    )


# ============================================================
# DECISION LOGIC
# ============================================================

def classify_decision(total_trust):

    if total_trust >= 70:
        return "allow"

    elif total_trust >= 40:
        return "limit"

    else:
        return "deny"


# ============================================================
# CONFUSION MATRIX
# ============================================================

def create_confusion_matrix(samples):

    labels = ["allow", "limit", "deny"]

    label_index = {
        label: index
        for index, label in enumerate(labels)
    }

    matrix = np.zeros((3, 3), dtype=int)

    for sample in samples:

        total_trust = calculate_total_trust(
            sample["CT"],
            sample["BT"],
            sample["ET"]
        )

        predicted = classify_decision(total_trust)
        expected = sample["expected"]

        matrix[
            label_index[expected],
            label_index[predicted]
        ] += 1

    return matrix, labels


# ============================================================
# CLASS METRICS
# ============================================================

def calculate_class_metrics(matrix, labels):

    print("\nClass Metrics")
    print("-" * 70)

    for i, label in enumerate(labels):

        tp = matrix[i, i]

        fp = matrix[:, i].sum() - tp
        fn = matrix[i, :].sum() - tp

        precision = (
            tp / (tp + fp)
            if (tp + fp) > 0
            else 0
        )

        recall = (
            tp / (tp + fn)
            if (tp + fn) > 0
            else 0
        )

        f1 = (
            2 * precision * recall
            / (precision + recall)
            if (precision + recall) > 0
            else 0
        )

        support = matrix[i, :].sum()

        print(
            f"{label.capitalize():<8} "
            f"Precision={precision * 100:6.1f}%  "
            f"Recall={recall * 100:6.1f}%  "
            f"F1={f1 * 100:6.1f}%  "
            f"Support={support}"
        )


# ============================================================
# CONFUSION MATRIX GRAPH
# ============================================================

def plot_confusion_matrix(matrix, labels):

    correct = np.trace(matrix)
    total = matrix.sum()
    accuracy = correct / total

    display_labels = [
        label.capitalize()
        for label in labels
    ]

    fig, ax = plt.subplots(
        figsize=(7.2, 5.6)
    )

    # Draw cells manually so colours are easy to control.
    for i in range(3):
        for j in range(3):

            if i == j:
                # Correct predictions
                face_colour = "#9be3a6"
            else:
                # Misclassified cases
                face_colour = "#d3d3d3"

            rectangle = plt.Rectangle(
                (j - 0.5, i - 0.5),
                1,
                1,
                facecolor=face_colour,
                edgecolor="white",
                linewidth=1.3
            )

            ax.add_patch(rectangle)

            ax.text(
                j,
                i,
                str(matrix[i, j]),
                ha="center",
                va="center",
                fontsize=12,
                color="black"
            )

    ax.set_xlim(-0.5, 2.5)
    ax.set_ylim(2.5, -0.5)

    ax.set_xticks(range(3))
    ax.set_yticks(range(3))

    ax.set_xticklabels(
        display_labels,
        fontsize=11
    )

    ax.set_yticklabels(
        display_labels,
        fontsize=11
    )

    ax.set_xlabel(
        "Predicted Decision",
        fontsize=12,
        labelpad=12
    )

    ax.set_ylabel(
        "Expected Decision",
        fontsize=12,
        labelpad=12
    )

    ax.set_title(
        "Expected vs Predicted Decision",
        fontsize=14,
        pad=14
    )

    # Remove outside frame.
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.tick_params(length=0)

    fig.tight_layout()

    # Save publication-quality outputs.
    png_path = os.path.join(
        OUTPUT_DIR,
        "trust_decision_confusion_matrix.png"
    )

    pdf_path = os.path.join(
        OUTPUT_DIR,
        "trust_decision_confusion_matrix.pdf"
    )

    svg_path = os.path.join(
        OUTPUT_DIR,
        "trust_decision_confusion_matrix.svg"
    )

    fig.savefig(
        png_path,
        dpi=600,
        bbox_inches="tight",
        facecolor="white"
    )

    fig.savefig(
        pdf_path,
        bbox_inches="tight",
        facecolor="white"
    )

    fig.savefig(
        svg_path,
        bbox_inches="tight",
        facecolor="white"
    )

    plt.close(fig)

    print("\nConfusion Matrix")
    print("-" * 50)
    print(matrix)

    print("\nOverall Result")
    print("-" * 50)
    print(f"Correct predictions : {correct}")
    print(f"Total scenarios     : {total}")
    print(f"Accuracy            : {accuracy * 100:.1f}%")

    print("\nSaved files")
    print("-" * 50)
    print(png_path)
    print(pdf_path)
    print(svg_path)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    # IMPORTANT:
    # Generate the 500 scenarios ONLY ONCE.
    canonical_samples = generate_synthetic_samples(
        n=N_SAMPLES,
        seed=SEED
    )

    matrix, labels = create_confusion_matrix(
        canonical_samples
    )

    plot_confusion_matrix(
        matrix,
        labels
    )

    calculate_class_metrics(
        matrix,
        labels
    )