"""基于关键词与经历证据的方向推荐。

不是“预测你适合什么”，而是给出 3 个大致契合、可解释的方向：
- 匹配到的技能/经历作为证据；
- 没匹配到的关键要求作为缺口；
- 三个方向尽量来自不同族（产品/技术/数据/运营），避免全是同一类。
"""

from __future__ import annotations

from typing import Any

DIRECTIONS = [
    {
        "name": "产品经理",
        "family": "产品",
        "keywords": ["产品", "需求", "PRD", "原型", "Axure", "用户调研", "竞品", "用户增长", "项目管理", "产品设计"],
        "desc": "需求分析、原型、PRD、跨团队推进",
    },
    {
        "name": "前端开发",
        "family": "技术",
        "keywords": ["HTML", "CSS", "JavaScript", "JS", "TypeScript", "React", "Vue", "小程序", "前端", "页面", "组件"],
        "desc": "页面/组件/交互实现，前端工程化",
    },
    {
        "name": "后端开发",
        "family": "技术",
        "keywords": ["Java", "Spring", "MySQL", "Redis", "微服务", "API", "后端", "服务端", "数据库", "并发"],
        "desc": "接口、服务、数据库与系统设计",
    },
    {
        "name": "数据分析",
        "family": "数据",
        "keywords": ["SQL", "Python", "Excel", "Tableau", "AB", "A/B", "数据分析", "统计", "可视化", "漏斗", "指标"],
        "desc": "取数、指标、实验分析、业务复盘",
    },
    {
        "name": "算法工程师",
        "family": "技术",
        "keywords": ["机器学习", "深度学习", "PyTorch", "TensorFlow", "模型", "算法", "NLP", "CV", "推荐", "特征工程"],
        "desc": "模型训练、特征工程、离线/在线评估",
    },
    {
        "name": "运营",
        "family": "运营",
        "keywords": ["运营", "活动", "用户增长", "社群", "内容", "新媒体", "转化", "拉新", "留存", "策划"],
        "desc": "活动、内容、用户与增长运营",
    },
    {
        "name": "测试开发",
        "family": "技术",
        "keywords": ["测试", "自动化", "Selenium", "用例", "质量", "接口测试", "性能测试"],
        "desc": "用例、自动化、质量保障",
    },
]

DEFAULT_TOP3 = ["产品经理", "数据分析", "运营"]


def _profile_text(profile: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(str(profile.get("job_intent", "")))
    parts.extend(str(x) for x in profile.get("skills", []))
    for e in profile.get("educations", []):
        parts.extend([str(e.get("major", "")), str(e.get("courses", ""))])
    for key in ("internships", "campus"):
        for item in profile.get(key, []):
            parts.extend([str(item.get("company", "")), str(item.get("org", "")),
                          str(item.get("role", "")), " ".join(str(b) for b in item.get("bullets", []))])
    return " ".join(parts).lower()


def _score(profile: dict[str, Any], text: str, direction: dict[str, Any]) -> dict[str, Any]:
    matched = [k for k in direction["keywords"] if k.lower() in text]
    missing = [k for k in direction["keywords"] if k.lower() not in text]
    coverage = min(1.0, len(matched) / 4.0)
    intent = str(profile.get("job_intent", "")).lower()
    boost = 0.25 if any(k.lower() in intent for k in direction["keywords"][:2]) else 0.0
    score = min(1.0, 0.75 * coverage + boost)
    if not matched:
        score = 0.08
    return {
        "name": direction["name"],
        "family": direction["family"],
        "score": round(score, 2),
        "matched": matched[:6],
        "missing": missing[:4],
        "desc": direction["desc"],
        "reason": ("匹配到 " + "、".join(matched[:4])) if matched else "暂未匹配到明显关键词，建议作为探索方向",
    }


def recommend_directions(profile: dict[str, Any], top_n: int = 3) -> list[dict[str, Any]]:
    text = _profile_text(profile)
    scored = [_score(profile, text, d) for d in DIRECTIONS]
    scored.sort(key=lambda x: x["score"], reverse=True)
    if not scored or scored[0]["score"] <= 0.08:
        # 没信息时给默认三方向
        by_name = {d["name"]: d for d in DIRECTIONS}
        return [{**_score(profile, text, by_name[n]), "score": 0.1} for n in DEFAULT_TOP3]

    # 尽量选不同族，避免三个都是技术
    picked: list[dict[str, Any]] = [scored[0]]
    used_families = {scored[0]["family"]}
    for item in scored[1:]:
        if len(picked) >= top_n:
            break
        if item["family"] not in used_families:
            picked.append(item)
            used_families.add(item["family"])
    for item in scored:
        if len(picked) >= top_n:
            break
        if item["name"] not in {p["name"] for p in picked}:
            picked.append(item)
    return picked[:top_n]
