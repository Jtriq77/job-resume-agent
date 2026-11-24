"""后端 ML 联合分析：分类 + 聚类 + 排序，一次跑在真实画像上。

用法：
    python scripts/ml_analyze.py --profile examples/sample_profile.json
输出：
    experiments/results/ml_demo.json
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.ml.ranker import FEATURES, build_features  # noqa: E402
from src.ml.text_clf import TfidfNB  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="examples/sample_profile.json")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()
    profile = json.loads((ROOT / args.profile).read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (ROOT / "data" / "jobs_sample.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

    clf = TfidfNB.load(ROOT / "models" / "family_clf.pkl")
    with (ROOT / "models" / "job_kmeans.pkl").open("rb") as f:
        bundle = pickle.load(f)
    vec, km = bundle["vectorizer"], bundle["kmeans"]
    ranker = json.loads((ROOT / "models" / "job_ranker.json").read_text(encoding="utf-8"))
    w = np.array(ranker["w"], dtype=np.float64)
    b = float(ranker["b"])

    scored = []
    for job in rows:
        feats = build_features(profile, job)
        x = np.array([feats[f] for f in FEATURES], dtype=np.float64)
        score = float(1.0 / (1.0 + np.exp(-(x @ w + b))))
        scored.append({"job": job, "score": score, "features": feats})
    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[: args.top]
    for item in top:
        job = item["job"]
        cat, prob, _ = clf.predict_one(str(job.get("title", "")), str(job.get("jd_text", "")))
        text = f"{job.get('title','')} {job.get('title','')} {str(job.get('jd_text',''))[:1800]}"
        cluster = int(km.predict(vec.transform([text]))[0])
        item.update({"predicted_category": cat, "category_prob": round(float(prob), 4), "cluster": cluster})
    result = {
        "profile": profile.get("name", ""),
        "method": "family classifier + KM++ cluster + LR ranker",
        "top": [
            {
                "job_id": x["job"].get("job_id"),
                "title": x["job"].get("title"),
                "company": x["job"].get("company"),
                "category": x["job"].get("category"),
                "predicted_category": x["predicted_category"],
                "category_prob": x["category_prob"],
                "cluster": x["cluster"],
                "ranker_score": round(x["score"], 4),
                "features": x["features"],
            }
            for x in top
        ],
    }
    (ROOT / "experiments" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "experiments" / "results" / "ml_demo.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["top"][:5], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
