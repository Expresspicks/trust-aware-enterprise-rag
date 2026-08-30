import os
import random
import numpy as np
import matplotlib.pyplot as plt

# -------------------------------------------------
# Settings
# -------------------------------------------------
random.seed(42)
np.random.seed(42)

OUTPUT_DIR = "trust_simulation_graphs"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -------------------------------------------------
# Synthetic Scenario Generator
# -------------------------------------------------
def generate_synthetic_samples(n=500):
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
        scenario = random.choice(scenario_types)

        if scenario == "admin_normal":
            ct = random.randint(90, 100)
            bt = random.randint(85, 100)
            et = random.randint(80, 100)
            expected = "allow"

        elif scenario == "manager_normal":
            ct = random.randint(80, 90)
            bt = random.randint(80, 100)
            et = random.randint(75, 95)
            expected = "allow"

        elif scenario == "sales_rep_own_region":
            ct = random.randint(70, 80)
            bt = random.randint(75, 100)
            et = random.randint(75, 95)
            expected = "allow"

        elif scenario == "sales_rep_other_region":
            ct = random.randint(15, 35)
            bt = random.randint(60, 95)
            et = random.randint(70, 95)
            expected = "deny"

        elif scenario == "intern_finance":
            ct = random.randint(10, 30)
            bt = random.randint(60, 90)
            et = random.randint(70, 95)
            expected = "deny"

        elif scenario == "sensitive_query":
            ct = random.randint(5, 25)
            bt = random.randint(20, 60)
            et = random.randint(20, 70)
            expected = "deny"

        elif scenario == "weak_evidence":
            ct = random.randint(60, 90)
            bt = random.randint(70, 100)
            et = random.randint(10, 40)
            expected = "limit"

        elif scenario == "suspicious_behaviour":
            ct = random.randint(50, 80)
            bt = random.randint(10, 40)
            et = random.randint(60, 90)
            expected = "limit"

        elif scenario == "rag_strong_evidence":
            ct = random.randint(70, 90)
            bt = random.randint(75, 100)
            et = random.randint(80, 100)
            expected = "allow"

        elif scenario == "rag_weak_evidence":
            ct = random.randint(60, 85)
            bt = random.randint(70, 100)
            et = random.randint(15, 45)
            expected = "limit"

        samples.append(
            {"scenario": scenario, "CT": ct, "BT": bt, "ET": et, "expected": expected}
        )

    return samples


# -------------------------------------------------
# Trust Formula
# -------------------------------------------------
def calculate_total_trust(ct, bt, et, alpha=0.4, beta=0.3, gamma=0.3):
    return round((alpha * ct) + (beta * bt) + (gamma * et), 2)


# -------------------------------------------------
# Decision Logic
# -------------------------------------------------
def classify_decision(total_trust):
    if total_trust >= 70:
        return "allow"
    elif total_trust >= 40:
        return "limit"
    else:
        return "deny"


# -------------------------------------------------
# Confusion Matrix
# -------------------------------------------------
def create_confusion_matrix(samples, alpha=0.4, beta=0.3, gamma=0.3):
    labels = ["deny", "limit", "allow"]
    label_index = {label: i for i, label in enumerate(labels)}

    matrix = np.zeros((3, 3), dtype=int)

    for sample in samples:
        tt = calculate_total_trust(
            sample["CT"], sample["BT"], sample["ET"], alpha, beta, gamma
        )

        predicted = classify_decision(tt)
        expected = sample["expected"]

        matrix[label_index[expected]][label_index[predicted]] += 1

    return matrix, labels


def plot_confusion_matrix(matrix, labels, alpha=0.4, beta=0.3, gamma=0.3):
    correct = np.trace(matrix)
    total = np.sum(matrix)
    accuracy = correct / total

    plt.figure(figsize=(7, 6))
    plt.imshow(matrix)

    plt.title(f"Confusion Matrix: TT = {alpha}CT + {beta}BT + {gamma}ET")
    plt.xlabel("Predicted Decision")
    plt.ylabel("Expected Decision")

    plt.xticks(range(len(labels)), labels)
    plt.yticks(range(len(labels)), labels)

    for i in range(len(labels)):
        for j in range(len(labels)):
            plt.text(j, i, matrix[i, j], ha="center", va="center", fontsize=13)

    plt.tight_layout()

    file_path = os.path.join(OUTPUT_DIR, "confusion_matrix_selected_formula.png")
    plt.savefig(file_path, dpi=300)
    plt.show()

    print("\nConfusion Matrix")
    print("-" * 40)
    print(matrix)

    print("\nResult")
    print("-" * 40)
    print(f"Correct predictions: {correct}")
    print(f"Total samples: {total}")
    print(f"Accuracy: {accuracy:.4f}")
    print(f"Saved graph to: {os.path.abspath(file_path)}")


# -------------------------------------------------
# Main Run
# -------------------------------------------------
if __name__ == "__main__":
    samples = generate_synthetic_samples(500)

    matrix, labels = create_confusion_matrix(samples, alpha=0.4, beta=0.3, gamma=0.3)

    plot_confusion_matrix(matrix, labels, alpha=0.4, beta=0.3, gamma=0.3)
