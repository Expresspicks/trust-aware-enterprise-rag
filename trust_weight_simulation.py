import random
import random
import numpy as np
import matplotlib.pyplot as plt
from itertools import product
from collections import defaultdict
import os

random.seed(42)
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
            {
                "scenario": scenario,
                "CT": ct,
                "BT": bt,
                "ET": et,
                "expected": expected,
            }
        )

    return samples


# -------------------------------------------------
# Trust Decision Logic
# -------------------------------------------------
def calculate_total_trust(ct, bt, et, w_ct, w_bt, w_et):
    return round((w_ct * ct) + (w_bt * bt) + (w_et * et), 2)


def classify_decision(total_trust):
    if total_trust >= 70:
        return "allow"
    elif total_trust >= 40:
        return "limit"
    else:
        return "deny"


# -------------------------------------------------
# Evaluation
# -------------------------------------------------
def evaluate_weights(samples, w_ct, w_bt, w_et):
    correct = 0

    for sample in samples:
        total_trust = calculate_total_trust(
            sample["CT"],
            sample["BT"],
            sample["ET"],
            w_ct,
            w_bt,
            w_et,
        )

        predicted = classify_decision(total_trust)

        if predicted == sample["expected"]:
            correct += 1

    accuracy = correct / len(samples)

    return round(accuracy, 4)


# -------------------------------------------------
# Grid Search Weight Testing
# -------------------------------------------------
def run_weight_simulation():
    samples = generate_synthetic_samples(500)

    results = []

    weight_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    for w_ct, w_bt, w_et in product(weight_values, repeat=3):
        if round(w_ct + w_bt + w_et, 1) == 1.0:
            accuracy = evaluate_weights(samples, w_ct, w_bt, w_et)

            results.append(
                {
                    "w_ct": w_ct,
                    "w_bt": w_bt,
                    "w_et": w_et,
                    "accuracy": accuracy,
                }
            )

    results = sorted(results, key=lambda x: x["accuracy"], reverse=True)

    print("\nTop Weight Combinations")
    print("-" * 60)

    for i, result in enumerate(results[:10], start=1):
        print(
            f"{i}. CT={result['w_ct']}, "
            f"BT={result['w_bt']}, "
            f"ET={result['w_et']} "
            f"=> Accuracy={result['accuracy']}"
        )

    print("\nSuggested Formula")
    print("-" * 60)

    target_accuracy = evaluate_weights(samples, 0.4, 0.3, 0.3)

    print(f"TT = 0.4CT + 0.3BT + 0.3ET")
    print(f"Accuracy = {target_accuracy}")

    print("\nSample Output Cases")
    print("-" * 60)

    for sample in samples[:10]:
        total_trust = calculate_total_trust(
            sample["CT"],
            sample["BT"],
            sample["ET"],
            0.4,
            0.3,
            0.3,
        )

        predicted = classify_decision(total_trust)

        print(
            f"Scenario={sample['scenario']}, "
            f"CT={sample['CT']}, BT={sample['BT']}, ET={sample['ET']}, "
            f"TT={total_trust}, Expected={sample['expected']}, Predicted={predicted}"
        )


###Plotting graphs###
def plot_top_weight_results():
    samples = generate_synthetic_samples(500)

    results = []
    weight_values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]

    for w_ct, w_bt, w_et in product(weight_values, repeat=3):
        if round(w_ct + w_bt + w_et, 1) == 1.0:
            accuracy = evaluate_weights(samples, w_ct, w_bt, w_et)

            results.append(
                {"label": f"{w_ct}CT + {w_bt}BT + {w_et}ET", "accuracy": accuracy}
            )

    results = sorted(results, key=lambda x: x["accuracy"], reverse=True)
    top_results = results[:10]

    labels = [r["label"] for r in top_results]
    accuracies = [r["accuracy"] for r in top_results]

    plt.figure(figsize=(12, 6))
    plt.bar(labels, accuracies)
    plt.xlabel("Weight Combination")
    plt.ylabel("Accuracy")
    plt.title("Accuracy Comparison of Trust Weight Combinations")
    plt.xticks(rotation=45, ha="right")
    plt.ylim(0, 1)
    plt.tight_layout()

    file_path = os.path.join(OUTPUT_DIR, "trust_weight_accuracy_bar_chart.png")
    plt.savefig(file_path, dpi=300)
    plt.close()

    print(f"Saved: {file_path}")


###Confusion Matrix####


def plot_confusion_matrix_for_selected_formula():
    samples = generate_synthetic_samples(500)

    labels = ["allow", "limit", "deny"]
    matrix = np.zeros((3, 3), dtype=int)

    label_index = {label: i for i, label in enumerate(labels)}

    for sample in samples:
        tt = calculate_total_trust(
            sample["CT"], sample["BT"], sample["ET"], 0.4, 0.3, 0.3
        )

        predicted = classify_decision(tt)
        expected = sample["expected"]

        matrix[label_index[expected]][label_index[predicted]] += 1

    plt.figure(figsize=(7, 6))
    plt.imshow(matrix)
    plt.title("Expected vs Predicted Decision")
    plt.xlabel("Predicted Decision")
    plt.ylabel("Expected Decision")

    plt.xticks(range(len(labels)), labels)
    plt.yticks(range(len(labels)), labels)

    for i in range(len(labels)):
        for j in range(len(labels)):
            plt.text(j, i, matrix[i, j], ha="center", va="center")

    plt.tight_layout()

    file_path = os.path.join(OUTPUT_DIR, "trust_decision_confusion_matrix.png")
    plt.savefig(file_path, dpi=300)
    plt.show()

    print(f"Saved: {file_path}")


def plot_average_tt_by_scenario():
    samples = generate_synthetic_samples(500)

    scenario_scores = defaultdict(list)

    for sample in samples:
        tt = calculate_total_trust(
            sample["CT"], sample["BT"], sample["ET"], 0.4, 0.3, 0.3
        )

        scenario_scores[sample["scenario"]].append(tt)

    scenarios = list(scenario_scores.keys())
    averages = [sum(scenario_scores[s]) / len(scenario_scores[s]) for s in scenarios]

    plt.figure(figsize=(12, 6))
    plt.bar(scenarios, averages)

    plt.axhline(y=70, linestyle="--", label="Allow threshold")
    plt.axhline(y=40, linestyle="--", label="Deny/Limit threshold")

    plt.xlabel("Scenario Type")
    plt.ylabel("Average Total Trust Score")
    plt.title("Average Total Trust Score by Scenario Type")
    plt.xticks(rotation=45, ha="right")
    plt.ylim(0, 100)
    plt.legend()
    plt.tight_layout()

    file_path = os.path.join(OUTPUT_DIR, "average_tt_by_scenario.png")
    plt.savefig(file_path, dpi=300)
    plt.close()

    print(f"Saved: {file_path}")


if __name__ == "__main__":
    run_weight_simulation()

    plot_top_weight_results()
    plot_confusion_matrix_for_selected_formula()
    plot_average_tt_by_scenario()
