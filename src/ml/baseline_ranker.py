"""匹配排序的基线：技能覆盖 + 标题关键词 + 城市/学历规则。

这不是最终 ML 模型，只是可运行的 baseline：
- 让 Agent 在标注数据到位前也能给出可解释排序；
- 报告里作为 B1 基线，与后续 LR/LambdaRank 对比；
- 前端事件会明确标注 tool=bm25_skill_baseline，不冒充 ML。
"""

from __future__ import annotations

import re
from typing import Any

EN_RE = re.compile(r"[a-z0-9+#.]+")
ZH_RE = re.compile(r"[\u4e00-\u9fff]+")

DEGREE_ORDER = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


def _tokens(text: str) -> set[str]:
    text = (text or "").lower()
    out = set(EN_RE.findall(text))
    for seq in ZH_RE.findall(text):
        out.update(seq[i:i + 2] for i in range(max(0, len(seq) - 1)))
    return out


class SkillBaselineRanker:
    def __init__(self, w_skill: float = 0.55, w_title: float = 0.25, w_city: float = 0.1, w_edu: float = 0.1):
        self.w_skill = w_skill
        self.w_title = w_title
        self.w_city = w_city
        self.w_edu = w_edu

    def score(self, profile: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
        skills = [str(s).lower() for s in (profile.get("skills") or []) if str(s).strip()]
        text = f"{job.get('title','')} {job.get('jd_text','')}".lower()
        matched = [s for s in skills if s in text]
        missing = [s for s in skills if s not in text]
        skill_cov = len(matched) / len(skills) if skills else 0.0

        target_tokens: set[str] = set()
        for f in (profile.get("job_intent") or []):
            target_tokens |= _tokens(str(f))
        title_tokens = _tokens(str(job.get("title", "")))
        title_hit = len(target_tokens & title_tokens) / max(1, len(target_tokens))

        target_cities = set(profile.get("target_cities") or [])
        cities = set(job.get("cities") or [])
        city_match = 1.0 if not target_cities or (target_cities & cities) else 0.0

        edu = profile.get("degree", "本科")
        req = job.get("degree_min") or "本科"
        edu_match = 1.0 if DEGREE_ORDER.get(edu, 2) >= DEGREE_ORDER.get(req, 2) else 0.0

        score = (
            self.w_skill * skill_cov
            + self.w_title * title_hit
            + self.w_city * city_match
            + self.w_edu * edu_match
        )
        return {
            "job_id": job.get("job_id"),
            "score": round(score, 4),
            "matched_skills": matched,
            "missing_skills": missing[:8],
            "evidence": {
                "skill_coverage": round(skill_cov, 3),
                "title_hit": round(title_hit, 3),
                "city_match": city_match,
                "edu_match": edu_match,
            },
        }

    def rank(self, profile: dict[str, Any], jobs: list[dict[str, Any]], top_k: int = 10) -> list[dict[str, Any]]:
        scored = []
        for j in jobs:
            s = self.score(profile, j)
            scored.append({**j, **s})
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]
