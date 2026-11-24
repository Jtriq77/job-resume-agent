"""训练/评估逻辑回归排序器：NDCG@5/10、Recall@5，对比技能覆盖基线。"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.ml.ranker import FEATURES, LogisticRanker, ndcg_at_k, recall_at_k  # noqa: E402


def main() -> None:
    rows = list(csv.DictReader((ROOT / "data" / "ranker_pairs.csv").open(encoding="utf-8")))
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    X = np.array([[float(r[f]) for f in FEATURES] for r in train], dtype=np.float64)
    y = np.array([float(r["label"]) for r in train], dtype=np.float64)
    model = LogisticRanker(lr=0.1, epochs=500, l2=1e-3).fit(X, y)
    model.save(ROOT / "models" / "job_ranker.json")

    by_profile: dict[str, list[dict]] = {}
    for r in test:
        by_profile.setdefault(r["profile_id"], []).append(r)
    metrics = {}
    for pid, items in by_profile.items():
        for r in items:
            x = np.array([[float(r[f]) for f in FEATURES]])
            r["model_score"] = float(model.predict_proba(x)[0])
        model_rank = sorted(items, key=lambda r: r["model_score"], reverse=True)
        base_rank = sorted(items, key=lambda r: float(r["baseline_score"]), reverse=True)
        m_rel = [int(r["label"]) for r in model_rank]
        b_rel = [int(r["label"]) for r in base_rank]
        metrics[pid] = {
            "n_test": len(items),
            "positive": sum(m_rel),
            "model": {
                "ndcg@5": round(ndcg_at_k(m_rel, 5), 4),
                "ndcg@10": round(ndcg_at_k(m_rel, 10), 4),
                "recall@5": round(recall_at_k(m_rel, 5), 4),
            },
            "baseline": {
                "ndcg@5": round(ndcg_at_k(b_rel, 5), 4),
                "ndcg@10": round(ndcg_at_k(b_rel, 10), 4),
                "recall@5": round(recall_at_k(b_rel, 5), 4),
            },
        }
    avg = {}
    for key in ("ndcg@5", "ndcg@10", "recall@5"):
        avg[key] = {
            "model": round(float(np.mean([m["model"][key] for m in metrics.values()])), 4),
            "baseline": round(float(np.mean([m["baseline"][key] for m in metrics.values()])), 4),
        }
    result = {
        "method": "feature engineering + L2 logistic regression (pointwise LTR)",
        "features": FEATURES,
        "train_pairs": len(train),
        "test_pairs": len(test),
        "per_profile": metrics,
        "average": avg,
        "label_note": "弱标注：仅按岗位族匹配生成；不是人工相关性标注，不能当作真实业务 NDCG。",
    }
    (ROOT / "experiments" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "experiments" / "results" / "ranker_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"train": len(train), "test": len(test), "average": avg}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
