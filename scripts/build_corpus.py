"""从 job_radar SQLite 分层抽样，生成岗位族分类/匹配排序用的语料。

用法：
    python scripts/build_corpus.py --per-category 300

输出：
    data/jobs_sample.jsonl
    data/sampling_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

CATEGORIES = [
    "技术", "产品", "运营", "设计", "市场销售", "职能",
    "金融", "医药", "工程制造", "管培", "项目管理", "教育培训",
]
OTHER_CATEGORIES = ["门店零售", "酒店物业", "科研", "地产物业"]

SNAPSHOT = "2026-11-23T01:53:40Z"


def stable_key(seed: int, job_id: str) -> str:
    return hashlib.md5(f"{seed}:{job_id}".encode("utf-8")).hexdigest()


def fetch_ids(con: sqlite3.Connection, category: str, recruit_type: str, limit: int, seed: int) -> list[dict]:
    rows = con.execute(
        """
        SELECT j.id, j.title, j.category, j.subcategory, j.recruit_type, j.grad_year,
               j.cities, j.degree_min, j.url, j.apply_end, c.name AS company
        FROM job j
        JOIN company c ON c.id = j.company_id
        WHERE j.category = ?
          AND j.recruit_type = ?
          AND j.title IS NOT NULL AND j.title != ''
          AND EXISTS (
              SELECT 1 FROM jd.job_text t
              WHERE t.job_id = j.id
                AND (length(coalesce(t.description,'')) > 20 OR length(coalesce(t.requirements,'')) > 20)
          )
        """,
        (category, recruit_type),
    ).fetchall()
    items = [
        {
            "job_id": r[0], "title": r[1], "category": r[2], "subcategory": r[3],
            "recruit_type": r[4], "grad_year": r[5], "cities": r[6],
            "degree_min": r[7], "url": r[8], "apply_end": r[9], "company": r[10],
        }
        for r in rows
    ]
    items.sort(key=lambda x: stable_key(seed, x["job_id"]))
    return items[:limit]


def fetch_text(con: sqlite3.Connection, ids: list[str]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for i in range(0, len(ids), 400):
        batch = ids[i:i + 400]
        q = ",".join("?" * len(batch))
        for jid, desc, req in con.execute(
            f"SELECT job_id, description, requirements FROM jd.job_text WHERE job_id IN ({q})", batch
        ):
            out[jid] = (desc or "", req or "")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-db", default="data/_raw_jobradar/jobs.db")
    ap.add_argument("--jd-db", default="data/_raw_jobradar/jd_text.db")
    ap.add_argument("--out", default="data/jobs_sample.jsonl")
    ap.add_argument("--report", default="data/sampling_report.json")
    ap.add_argument("--per-category", type=int, default=300)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    con = sqlite3.connect(args.jobs_db)
    con.execute("ATTACH DATABASE ? AS jd", (args.jd_db,))

    all_items: list[dict] = []
    report: dict = {"per_category_target": args.per_category, "categories": {}, "snapshot": SNAPSHOT}

    for cat in CATEGORIES + ["其他"]:
        cats = OTHER_CATEGORIES if cat == "其他" else [cat]
        target = args.per_category
        campus_n = int(target * 0.7)
        intern_n = target - campus_n
        picked: list[dict] = []
        for rt, n in (("campus", campus_n), ("intern", intern_n)):
            pool: list[dict] = []
            for c in cats:
                pool.extend(fetch_ids(con, c, rt, 2000, args.seed))
            pool.sort(key=lambda x: stable_key(args.seed, x["job_id"]))
            seen = {x["job_id"] for x in picked}
            got = 0
            for x in pool:
                if x["job_id"] in seen:
                    continue
                picked.append(x)
                seen.add(x["job_id"])
                got += 1
                if got >= n:
                    break
        if len(picked) < target:
            pool = []
            for c in cats:
                for rt in ("campus", "intern"):
                    pool.extend(fetch_ids(con, c, rt, 2000, args.seed))
            pool.sort(key=lambda x: stable_key(args.seed, x["job_id"]))
            seen = {x["job_id"] for x in picked}
            for x in pool:
                if x["job_id"] not in seen:
                    picked.append(x)
                    seen.add(x["job_id"])
                    if len(picked) >= target:
                        break
        picked = picked[:target]
        for item in picked:
            item["category"] = cat
        report["categories"][cat] = {
            "picked": len(picked),
            "campus": sum(1 for x in picked if x["recruit_type"] == "campus"),
            "intern": sum(1 for x in picked if x["recruit_type"] == "intern"),
        }
        all_items.extend(picked)

    texts = fetch_text(con, [x["job_id"] for x in all_items])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    with out_path.open("w", encoding="utf-8") as f:
        for item in all_items:
            desc, req = texts.get(item["job_id"], ("", ""))
            if len(desc) + len(req) < 20:
                continue
            try:
                cities = json.loads(item["cities"]) if item["cities"] else []
            except Exception:  # noqa: BLE001
                cities = []
            row = {
                **item,
                "cities": cities,
                "jd_text": (desc + "\n" + req).strip(),
                "source": "job_radar",
                "snapshot": SNAPSHOT,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            kept += 1

    report["kept"] = kept
    report["by_category"] = dict(Counter(x["category"] for x in all_items))
    report["by_recruit_type"] = dict(Counter(x["recruit_type"] for x in all_items))
    report["avg_jd_chars"] = round(
        sum(len(t[0]) + len(t[1]) for t in texts.values()) / max(1, len(texts)), 1
    )
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out_path}：{kept} 条")
    print(f"报告 {args.report}")
    print(json.dumps(report["categories"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
