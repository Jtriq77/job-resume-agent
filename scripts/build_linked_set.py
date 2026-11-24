"""生成 30–40 条带链接的演示岗位 + 公司分层表。

用法：
    python scripts/build_linked_set.py --max 40

输出：
    data/jobs_linked.jsonl
    data/companies.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

COMPANIES = [
    # 大厂（冲刺）
    ("字节跳动", "大厂", "互联网", "万人以上"),
    ("阿里巴巴", "大厂", "互联网/电商", "万人以上"),
    ("腾讯", "大厂", "互联网/游戏", "万人以上"),
    ("百度", "大厂", "互联网/AI", "万人以上"),
    ("美团", "大厂", "本地生活", "万人以上"),
    ("滴滴", "大厂", "出行", "万人以上"),
    ("快手", "大厂", "短视频", "万人以上"),
    ("小红书", "大厂", "社区/电商", "万人以上"),
    ("京东", "大厂", "电商/物流", "万人以上"),
    ("小米", "大厂", "消费电子", "万人以上"),
    # 中厂（匹配）
    ("哔哩哔哩", "中厂", "内容社区", "数千人"),
    ("得物App", "中厂", "电商", "数千人"),
    ("蔚来", "中厂", "新能源汽车", "万人以上"),
    ("小鹏汽车", "中厂", "新能源汽车", "万人以上"),
    ("金山云", "中厂", "云计算", "数千人"),
    ("科大讯飞", "中厂", "AI", "万人以上"),
    ("阅文集团", "中厂", "数字阅读", "数千人"),
    ("万兴科技", "中厂", "软件", "数千人"),
    ("地平线", "中厂", "智能驾驶芯片", "数千人"),
    ("拓竹科技", "中厂", "3D 打印", "数千人"),
    # 小厂/成长型（保底）
    ("51WORLD", "小厂", "数字孪生", "数百人"),
    ("海柔创新", "小厂", "仓储机器人", "数千人"),
    ("仙工智能", "小厂", "移动机器人", "数百人"),
    ("云圣智能", "小厂", "工业无人机", "数百人"),
    ("优艾智合", "小厂", "移动机器人", "数百人"),
    ("轻舟智航", "小厂", "自动驾驶", "数百人"),
    ("越疆科技", "小厂", "协作机器人", "数千人"),
    ("思必驰", "小厂", "语音 AI", "数千人"),
    ("普渡机器人", "小厂", "服务机器人", "数千人"),
    ("沐瞳科技", "小厂", "游戏", "数千人"),
]

TARGET_CYCLE = ["产品", "运营", "技术"]

TIER_REASON = {
    "大厂": "校招规模大、品牌知名度高、竞争激烈，作为冲刺",
    "中厂": "细分领域知名/上市公司/数千人规模，作为匹配",
    "小厂": "成长型/中小型公司，流程相对短，作为保底",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs-db", default="data/_raw_jobradar/jobs.db")
    ap.add_argument("--jd-db", default="data/_raw_jobradar/jd_text.db")
    ap.add_argument("--out", default="data/jobs_linked.jsonl")
    ap.add_argument("--companies-out", default="data/companies.csv")
    ap.add_argument("--max", type=int, default=40)
    ap.add_argument("--per-company", type=int, default=1)
    args = ap.parse_args()

    con = sqlite3.connect(args.jobs_db)
    con.execute("ATTACH DATABASE ? AS jd", (args.jd_db,))

    rows = []
    companies = []
    for idx, (name, tier, industry, size_stage) in enumerate(COMPANIES, start=1):
        target_cat = TARGET_CYCLE[(idx - 1) % len(TARGET_CYCLE)]
        jobs = con.execute(
            """
            SELECT j.id, j.title, j.category, j.subcategory, j.recruit_type, j.grad_year,
                   j.cities, j.degree_min, j.url, j.apply_end,
                   t.description, t.requirements
            FROM job j
            JOIN company c ON c.id = j.company_id
            JOIN jd.job_text t ON t.job_id = j.id
            WHERE c.name = ?
              AND j.recruit_type IN ('campus','intern')
              AND j.category IN ('产品','运营','技术')
              AND j.url IS NOT NULL AND j.url != ''
              AND (length(coalesce(t.description,'')) + length(coalesce(t.requirements,''))) > 40
            ORDER BY
              CASE WHEN j.category = ? THEN 0 ELSE 1 END,
              CASE WHEN j.title LIKE '%数据%' THEN 0 ELSE 1 END,
              j.last_seen DESC
            LIMIT 3
            """,
            (name, target_cat),
        ).fetchall()
        if not jobs:
            print(f"跳过（无岗位）：{name}")
            continue
        first = jobs[0]
        netloc = urlparse(first[8]).netloc or ""
        career_url = f"https://{netloc}/" if netloc else ""
        companies.append({
            "company_id": f"c{idx:03d}",
            "name": name,
            "tier": tier,
            "industry": industry,
            "size_stage": size_stage,
            "city": "",
            "career_url": career_url,
            "tier_reason": TIER_REASON[tier],
            "verified_at": "2026-11-23",
        })
        for j in jobs[:args.per_company]:
            if len(rows) >= args.max:
                break
            try:
                cities = json.loads(j[6]) if j[6] else []
            except Exception:  # noqa: BLE001
                cities = []
            rows.append({
                "job_id": j[0],
                "company_id": f"c{idx:03d}",
                "company": name,
                "tier": tier,
                "title": j[1],
                "category": j[2],
                "subcategory": j[3],
                "recruit_type": j[4],
                "grad_year": j[5],
                "cities": cities,
                "degree_min": j[7],
                "url": j[8],
                "career_url": career_url,
                "apply_end": j[9],
                "jd_text": ((j[10] or "") + "\n" + (j[11] or "")).strip(),
                "link_status": "unknown",
                "last_checked": "",
                "source": "job_radar",
                "snapshot": "2026-11-23T01:53:40Z",
            })

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    cpath = Path(args.companies_out)
    with cpath.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(companies[0].keys()))
        writer.writeheader()
        writer.writerows(companies)

    print(f"写入 {out}：{len(rows)} 条岗位")
    print(f"写入 {cpath}：{len(companies)} 家公司")


if __name__ == "__main__":
    main()
