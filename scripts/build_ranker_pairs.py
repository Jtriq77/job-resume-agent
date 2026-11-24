"""构造简历-岗位排序训练对（弱标注，供 LR 排序器训练/评估）。

重要：标签是规则弱标注，不是人工相关性标注；报告必须写清。
输出：
- data/ranker_pairs.csv
- data/ranker_profiles.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.baseline_ranker import SkillBaselineRanker  # noqa: E402
from src.ml.ranker import FEATURES, build_features  # noqa: E402


def profiles() -> dict[str, dict]:
    base = json.loads((ROOT / "examples" / "sample_profile.json").read_text(encoding="utf-8"))
    data = dict(base)
    data.update({
        "name": "候选人A",
        "job_intent": "数据分析",
        "degree": "本科",
        "target_cities": ["上海"],
        "skills": [
            "工具：SQL、Python（pandas）、Tableau、Excel",
            "方法：A/B 测试、漏斗分析、用户流失预测",
            "证书/其他：全国计算机二级",
        ],
        "_target_categories": ["技术", "产品", "运营", "金融"],
    })
    product = dict(data)
    product.update({
        "name": "候选人B",
        "job_intent": "产品经理",
        "skills": ["工具：Axure、Figma、SQL、Excel", "方法：需求分析、PRD、竞品分析、用户调研"],
        "_target_categories": ["产品", "运营"],
    })
    front = dict(data)
    front.update({
        "name": "候选人C",
        "job_intent": "前端开发",
        "degree": "本科",
        "skills": ["语言：JavaScript、TypeScript、HTML/CSS", "框架：React、Vue、Webpack"],
        "_target_categories": ["技术"],
    })
    back = dict(data)
    back.update({
        "name": "候选人D",
        "job_intent": "后端开发",
        "degree": "硕士",
        "skills": ["语言：Java、Go", "框架：Spring、MySQL、Redis、Linux、并发"],
        "_target_categories": ["技术"],
    })
    ops = dict(data)
    ops.update({
        "name": "候选人E",
        "job_intent": "运营",
        "skills": ["方法：活动策划、内容运营、用户增长、社群运营、数据分析"],
        "_target_categories": ["运营", "市场销售"],
    })
    return {"data": data, "product": product, "frontend": front, "backend": back, "ops": ops}


def weak_label(profile: dict, job: dict, feats: dict) -> int:
    # 只用岗位族做弱标签；不再用 skill_cov 参与标签，避免与特征泄漏
    return 1 if str(job.get("category", "")) in set(profile.get("_target_categories") or []) else 0


def main() -> None:
    rows = [json.loads(line) for line in (ROOT / "data" / "jobs_sample.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(str(r.get("category", "")), []).append(r)
    rng = random.Random(42)
    selected = []
    for cat, items in by_cat.items():
        selected.extend(rng.sample(items, min(40, len(items))))
    rng.shuffle(selected)
    ps = profiles()
    base = SkillBaselineRanker()
    out = []
    for pid, profile in ps.items():
        for job in selected:
            feats = build_features(profile, job)
            label = weak_label(profile, job, feats)
            baseline = base.score(profile, job)["score"]
            bucket = int(hashlib.md5(str(job["job_id"]).encode("utf-8")).hexdigest(), 16) % 10
            split = "test" if bucket < 2 else "train"
            out.append({"profile_id": pid, "job_id": job["job_id"], "split": split, "label": label,
                        "baseline_score": round(float(baseline), 4), **feats})
    with (ROOT / "data" / "ranker_pairs.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["profile_id", "job_id", "split", "label", "baseline_score", *FEATURES])
        w.writeheader()
        w.writerows(out)
    (ROOT / "data" / "ranker_profiles.json").write_text(json.dumps(ps, ensure_ascii=False, indent=2), encoding="utf-8")
    print("pairs", len(out), "positive", sum(x["label"] for x in out), "profiles", len(ps))


if __name__ == "__main__":
    main()
