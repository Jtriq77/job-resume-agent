"""生成 300 条人工金标准标注表（分层抽样）。

用法：
    python scripts/make_gold_set.py --n 300

输出：
    data/gold_300.csv       # 给标注者：job_id/title/company/jd_snippet/label/note
    data/gold_300_key.csv   # 规则标签，仅用于事后分析，不要给标注者看
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/jobs_sample.jsonl")
    ap.add_argument("--out", default="data/gold_300.csv")
    ap.add_argument("--key", default="data/gold_300_key.csv")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rows = [json.loads(line) for line in Path(args.input).read_text(encoding="utf-8").splitlines() if line.strip()]
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r)
    rng = random.Random(args.seed)
    cats = sorted(by_cat)
    per = args.n // len(cats)
    selected = []
    for c in cats:
        items = by_cat[c][:]
        rng.shuffle(items)
        selected.extend(items[:per])
    # 余数补齐
    remainder = args.n - len(selected)
    if remainder > 0:
        pool = [r for r in rows if r not in selected]
        rng.shuffle(pool)
        selected.extend(pool[:remainder])
    rng.shuffle(selected)

    out = Path(args.out)
    key = Path(args.key)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["gold_id", "job_id", "title", "company", "jd_snippet", "label", "note", "annotator"])
        w.writeheader()
        for i, r in enumerate(selected, start=1):
            w.writerow({
                "gold_id": f"g{i:03d}",
                "job_id": r["job_id"],
                "title": r["title"],
                "company": r.get("company", ""),
                "jd_snippet": r.get("jd_text", "")[:400].replace("\n", " "),
                "label": "",
                "note": "",
                "annotator": "",
            })
    with key.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["gold_id", "job_id", "category_rule"])
        w.writeheader()
        for i, r in enumerate(selected, start=1):
            w.writerow({"gold_id": f"g{i:03d}", "job_id": r["job_id"], "category_rule": r["category"]})
    print(f"写入 {out}：{len(selected)} 条")
    print(f"写入 {key}：规则标签，仅用于分析")
    print("类别分布：", {c: sum(1 for r in selected if r['category'] == c) for c in cats})


if __name__ == "__main__":
    main()
