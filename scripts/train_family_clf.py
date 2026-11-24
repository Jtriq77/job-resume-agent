"""训练岗位族分类器（TF-IDF + 多项式朴素贝叶斯）。

用法：
    python scripts/train_family_clf.py

输出：
    models/family_clf.pkl
    models/family_clf_card.json
    experiments/results/family_clf_metrics.json
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.text_clf import TfidfNB, confusion, prf, stratified_split  # noqa: E402


def evaluate(train: list[dict], test: list[dict], title_only: bool = False) -> tuple[dict, TfidfNB]:
    model = TfidfNB(max_features=30000, n_min=1, n_max=3, alpha=0.3)
    if title_only:
        for r in train:
            r = dict(r)
            r["jd_text"] = ""
        # 用一个只含标题的副本训练
        train_copy = [{**r, "jd_text": ""} for r in train]
        test_copy = [{**r, "jd_text": ""} for r in test]
        model.fit(train_copy)
        pred = model.predict(test_copy)
        true = [r["category"] for r in test_copy]
    else:
        model.fit(train)
        pred = model.predict(test)
        true = [r["category"] for r in test]
    labels = sorted({r["category"] for r in train})
    metrics = prf(true, pred, labels)
    metrics["confusion"] = confusion(true, pred, labels)
    metrics["n_train"] = len(train)
    metrics["n_test"] = len(test)
    return metrics, model


def main() -> None:
    path = ROOT / "data" / "jobs_sample.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    train, test = stratified_split(rows, test_ratio=0.2, seed=42)

    print(f"训练 {len(train)} / 测试 {len(test)}")
    print("训练主模型（标题 + 正文）...")
    main_metrics, model = evaluate(train, test, title_only=False)
    print(f"macro-F1={main_metrics['macro_f1']}  acc={main_metrics['accuracy']}  weighted-F1={main_metrics['weighted_f1']}")

    print("消融：只用标题...")
    title_metrics, _ = evaluate(train, test, title_only=True)
    print(f"macro-F1={title_metrics['macro_f1']}  acc={title_metrics['accuracy']}")

    # 多数类基线
    from collections import Counter
    majority = Counter(r["category"] for r in train).most_common(1)[0][0]
    base_pred = [majority] * len(test)
    base_metrics = prf([r["category"] for r in test], base_pred, sorted({r["category"] for r in train}))

    out = {
        "trained_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data": "data/jobs_sample.jsonl",
        "n_total": len(rows),
        "n_train": len(train),
        "n_test": len(test),
        "model": "TF-IDF (char 1-3 + en token) + MultinomialNB",
        "max_features": 30000,
        "alpha": 0.3,
        "main": main_metrics,
        "ablation_title_only": title_metrics,
        "baseline_majority": base_metrics,
        "note": "训练/测试标签来自 job_radar 的规则职类，不是人工金标准；需用 300 条人工标注复核。",
    }
    results = ROOT / "experiments" / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / "family_clf_metrics.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    model.save(ROOT / "models" / "family_clf.pkl")
    card = {
        "name": "job_family_clf",
        "version": "v1",
        "trained_at": out["trained_at"],
        "algorithm": out["model"],
        "classes": model.classes,
        "n_features": len(model.vocab),
        "data_source": "job_radar snapshot 2026-11-23",
        "train_size": len(train),
        "test_size": len(test),
        "macro_f1_silver": main_metrics["macro_f1"],
        "accuracy_silver": main_metrics["accuracy"],
        "title_only_macro_f1": title_metrics["macro_f1"],
        "majority_baseline_macro_f1": base_metrics["macro_f1"],
        "limitations": [
            "标签来自规则职类，不是人工金标准",
            "测试集与训练集同分布，未验证跨来源泛化",
            "类别边界（产品/运营、技术/数据）存在主观性",
        ],
    }
    (ROOT / "models" / "family_clf_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n各类 F1：")
    for c, v in main_metrics["per_class"].items():
        print(f"  {c:<6} P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f} n={v['support']}")
    print("\n写入 models/family_clf.pkl, models/family_clf_card.json, experiments/results/family_clf_metrics.json")


if __name__ == "__main__":
    main()
