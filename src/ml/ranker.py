"""特征工程 + 逻辑回归排序器（pointwise learning-to-rank）。

第三个 ML 知识点：
- 特征：技能覆盖、标题命中、简历-JD 余弦相似度、城市、学历、岗位族匹配；
- 模型：L2 正则逻辑回归，梯度下降训练；
- 评估：NDCG@5/10、Recall@5，与技能覆盖基线对比。

注意：当前训练标签是规则弱标注，不是人工相关性标注；报告必须写清。
"""

from __future__ import annotations

import json
import math
import pickle
from pathlib import Path
from typing import Any

import numpy as np

FEATURES = [
    "skill_cov",
    "title_hit",
    "text_cos",
    "city_match",
    "edu_match",
    "jd_len_norm",
    "title_len_norm",
]

DEGREE_ORDER = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}


class LogisticRanker:
    def __init__(self, lr: float = 0.08, epochs: int = 400, l2: float = 1e-3, seed: int = 42):
        self.lr = lr
        self.epochs = epochs
        self.l2 = l2
        self.seed = seed
        self.w: np.ndarray | None = None
        self.b: float = 0.0

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticRanker":
        rng = np.random.default_rng(self.seed)
        n, d = X.shape
        self.w = rng.normal(0, 0.01, size=d)
        self.b = 0.0
        for _ in range(self.epochs):
            z = X @ self.w + self.b
            p = 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))
            err = p - y
            gw = X.T @ err / n + self.l2 * self.w
            gb = float(err.mean())
            self.w -= self.lr * gw
            self.b -= self.lr * gb
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = X @ self.w + self.b
        return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps({"features": FEATURES, "w": self.w.tolist(), "b": self.b}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def tokens(text: str) -> set[str]:
    from src.ml.text_clf import features

    return set(features(text, 1, 2))


def _profile_text(profile: dict[str, Any]) -> str:
    parts = [str(profile.get("job_intent", ""))]
    for e in profile.get("educations", []):
        parts += [str(e.get("major", "")), str(e.get("courses", "")), str(e.get("extra", ""))]
    for it in profile.get("internships", []) + profile.get("campus", []):
        parts += [str(it.get("role", "")), str(it.get("company", "")), str(it.get("org", ""))]
        parts += [str(b) for b in it.get("bullets", [])]
    parts += [str(s) for s in profile.get("skills", [])]
    return " ".join(x for x in parts if x)


def _profile_skills(profile: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for s in profile.get("skills", []):
        text = str(s)
        if "：" in text:
            text = text.split("：", 1)[1]
        for x in text.replace("、", ",").replace("；", ",").replace(";", ",").split(","):
            x = x.strip().lower()
            if len(x) >= 2:
                out.append(x)
    return out


def build_features(profile: dict[str, Any], job: dict[str, Any]) -> dict[str, float]:
    job_text = f"{job.get('title','')} {job.get('jd_text','')}".lower()
    title = str(job.get("title", "")).lower()
    skills = _profile_skills(profile)
    matched = [s for s in skills if s in job_text]
    skill_cov = len(matched) / len(skills) if skills else 0.0

    intent = str(profile.get("job_intent", ""))
    intent_tokens = tokens(intent)
    title_tokens = tokens(title)
    title_hit = len(intent_tokens & title_tokens) / max(1, len(intent_tokens))

    ptext = _profile_text(profile).lower()
    pt = tokens(ptext)
    jt = tokens(job_text)
    inter = len(pt & jt)
    text_cos = inter / math.sqrt(max(1, len(pt)) * max(1, len(jt)))

    target_cities = set(profile.get("target_cities") or [])
    city_match = 1.0 if not target_cities or (target_cities & set(job.get("cities") or [])) else 0.0

    degree = profile.get("degree") or "本科"
    req = job.get("degree_min") or "本科"
    edu_match = 1.0 if DEGREE_ORDER.get(str(degree), 2) >= DEGREE_ORDER.get(str(req), 2) else 0.0

    jd_len = min(1.0, len(str(job.get("jd_text", ""))) / 3000.0)
    title_len = min(1.0, len(str(job.get("title", ""))) / 40.0)
    return {
        "skill_cov": round(skill_cov, 4),
        "title_hit": round(title_hit, 4),
        "text_cos": round(text_cos, 4),
        "city_match": city_match,
        "edu_match": edu_match,
        "jd_len_norm": round(jd_len, 4),
        "title_len_norm": round(title_len, 4),
    }


def ndcg_at_k(rels: list[int], k: int) -> float:
    rels = rels[:k]
    dcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(rels))
    ideal = sorted(rels, reverse=True)
    idcg = sum((2 ** r - 1) / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def recall_at_k(rels: list[int], k: int) -> float:
    total = sum(1 for r in rels if r > 0)
    return sum(1 for r in rels[:k] if r > 0) / total if total else 0.0
