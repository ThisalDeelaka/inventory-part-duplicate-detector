from pathlib import Path

import pandas as pd
from sklearn.metrics import precision_recall_fscore_support

from app.engine.scoring import score_candidate


def main():
    path = Path(__file__).resolve().parents[3] / "data" / "evaluation_pairs.csv"
    df = pd.read_csv(path)
    expected, predicted = [], []
    false_positives, false_negatives = [], []
    for _, row in df.iterrows():
        result = score_candidate({"PART_NO": "A", "DESCRIPTION": row.description_a}, {"PART_NO": "B", "DESCRIPTION": row.description_b}, [])
        actual = int(row.expected_label)
        guess = int(result["final_score"] >= 60)
        expected.append(actual); predicted.append(guess)
        item = {"description_a": row.description_a, "description_b": row.description_b, "score": result["final_score"]}
        if guess and not actual: false_positives.append(item)
        if actual and not guess: false_negatives.append(item)
    precision, recall, f1, _ = precision_recall_fscore_support(expected, predicted, average="binary", zero_division=0)
    print({"precision": round(precision, 3), "recall": round(recall, 3), "f1_score": round(f1, 3), "false_positives": false_positives, "false_negatives": false_negatives})


if __name__ == "__main__": main()
