"""TF-IDF + K-Means++ 岗位聚类（无监督 ML）。

为什么加这个：
- 分类器需要标签，聚类不需要；可以对 3,900 条岗位做无监督分群；
- 用轮廓系数选 k，用岗位族标签算纯度，作为分类之外的第二条 ML 证据；
- 纯 numpy 实现，和 text_clf 一样避开 sklearn 的签名问题。

输出：
- models/job_kmeans.pkl
- models/job_cluster_card.json
- experiments/results/job_cluster_metrics.json
- data/job_clusters.csv
"""

from __future__ import annotations

import json
import math
import pickle
import re
from collections import Counter
from pathlib import Path

import numpy as np

from src.ml.text_clf import features

ROOT = Path(__file__).resolve().parents[2]


class TfidfVectorizer:
    def __init__(self, max_features: int = 3000, min_df: int = 2, n_min: int = 1, n_max: int = 2):
        self.max_features = max_features
        self.min_df = min_df
        self.n_min = n_min
        self.n_max = n_max
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None

    def _tokens(self, text: str) -> list[str]:
        return features(text, self.n_min, self.n_max)

    def fit_transform(self, texts: list[str]) -> np.ndarray:
        df: Counter[str] = Counter()
        tokenized: list[list[str]] = []
        for t in texts:
            toks = self._tokens(t)
            tokenized.append(toks)
            df.update(set(toks))
        # 按 (词频降序, 词本身) 排序，避免哈希随机化导致词表顺序不稳定
        terms = [t for t, c in sorted(df.items(), key=lambda x: (-x[1], x[0])) if c >= self.min_df][: self.max_features]
        self.vocab = {t: i for i, t in enumerate(terms)}
        n = len(texts)
        self.idf = np.array([math.log((1 + n) / (1 + df[t])) + 1.0 for t in terms], dtype=np.float32)
        X = np.zeros((n, len(self.vocab)), dtype=np.float32)
        for i, toks in enumerate(tokenized):
            X[i] = self._vectorize_tokens(toks)
        return X

    def _vectorize_tokens(self, toks: list[str]) -> np.ndarray:
        counts: Counter[int] = Counter()
        for t in toks:
            j = self.vocab.get(t)
            if j is not None:
                counts[j] += 1
        vec = np.zeros(len(self.vocab), dtype=np.float32)
        if not counts:
            return vec
        for j, c in counts.items():
            vec[j] = 1.0 + math.log(c)
        vec *= self.idf
        norm = float(np.linalg.norm(vec))
        if norm:
            vec /= norm
        return vec

    def transform(self, texts: list[str]) -> np.ndarray:
        X = np.zeros((len(texts), len(self.vocab)), dtype=np.float32)
        for i, text in enumerate(texts):
            X[i] = self._vectorize_tokens(self._tokens(text))
        return X


class SphericalKMeans:
    """余弦距离的 K-Means++；向量先 L2 归一化，更新后重新归一化。"""

    def __init__(self, n_clusters: int = 8, max_iter: int = 30, n_init: int = 3, seed: int = 42):
        self.n_clusters = n_clusters
        self.max_iter = max_iter
        self.n_init = n_init
        self.seed = seed
        self.centroids: np.ndarray | None = None
        self.labels_: np.ndarray | None = None
        self.inertia_: float | None = None

    @staticmethod
    def _normalize(X: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(X, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return X / norms

    def _init_centroids(self, X: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        n = X.shape[0]
        first = int(rng.integers(n))
        centers = [X[first]]
        closest = 1.0 - X @ X[first]
        for _ in range(1, self.n_clusters):
            probs = np.maximum(closest, 0.0) ** 2
            total = probs.sum()
            if total <= 1e-12:
                idx = int(rng.integers(n))
            else:
                idx = int(rng.choice(n, p=probs / total))
            centers.append(X[idx])
            closest = np.minimum(closest, 1.0 - X @ X[idx])
        return self._normalize(np.vstack(centers))

    def fit(self, X: np.ndarray) -> "SphericalKMeans":
        X = self._normalize(X.astype(np.float32))
        best = None
        for run in range(self.n_init):
            rng = np.random.default_rng(self.seed + run)
            centers = self._init_centroids(X, rng)
            labels = np.zeros(X.shape[0], dtype=np.int64)
            for _ in range(self.max_iter):
                sims = X @ centers.T
                new_labels = np.argmax(sims, axis=1)
                if np.array_equal(new_labels, labels):
                    labels = new_labels
                    break
                labels = new_labels
                for k in range(self.n_clusters):
                    members = X[labels == k]
                    if len(members):
                        c = members.mean(axis=0)
                        n = np.linalg.norm(c)
                        centers[k] = c / n if n else c
                    else:
                        centers[k] = X[int(rng.integers(X.shape[0]))]
            inertia = float(np.mean(1.0 - np.max(X @ centers.T, axis=1)))
            if best is None or inertia < best[0]:
                best = (inertia, centers.copy(), labels.copy())
        self.inertia_, self.centroids, self.labels_ = best
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        X = self._normalize(X.astype(np.float32))
        return np.argmax(X @ self.centroids.T, axis=1)


def silhouette_cosine(X: np.ndarray, labels: np.ndarray, sample_size: int = 700, seed: int = 42) -> float:
    """余弦距离轮廓系数；样本内两两距离，O(sample^2)，适合几千条数据。"""
    n = X.shape[0]
    rng = np.random.default_rng(seed)
    idx = rng.choice(n, size=min(sample_size, n), replace=False)
    Xs = X[idx]
    ls = labels[idx]
    sims = Xs @ Xs.T
    dist = 1.0 - sims
    scores = []
    for i in range(len(idx)):
        own = ls == ls[i]
        own[i] = False
        if own.sum() == 0:
            continue
        a = float(dist[i, own].mean())
        b = float("inf")
        for k in set(ls.tolist()):
            if k == ls[i]:
                continue
            mask = ls == k
            if mask.sum():
                b = min(b, float(dist[i, mask].mean()))
        if b == float("inf"):
            continue
        s = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
        scores.append(s)
    return float(np.mean(scores)) if scores else 0.0


def purity(labels: np.ndarray, categories: list[str]) -> float:
    total = len(labels)
    if total == 0:
        return 0.0
    hit = 0
    for k in sorted(set(labels.tolist())):
        c = Counter(c for c, l in zip(categories, labels) if int(l) == k)
        hit += c.most_common(1)[0][1] if c else 0
    return hit / total


def cluster_terms(centroids: np.ndarray, vocab: dict[str, int], top_n: int = 8) -> list[list[str]]:
    inv = {i: t for t, i in vocab.items()}
    out = []
    for row in centroids:
        idx = np.argsort(row)[::-1][:top_n]
        out.append([inv[int(i)] for i in idx if int(i) in inv])
    return out


def cluster_jobs(rows: list[dict], k: int = 8, max_features: int = 3000, seed: int = 42) -> tuple[TfidfVectorizer, SphericalKMeans, np.ndarray]:
    texts = [f"{r.get('title','')} {r.get('title','')} {str(r.get('jd_text',''))[:1800]}" for r in rows]
    vec = TfidfVectorizer(max_features=max_features, min_df=2)
    X = vec.fit_transform(texts)
    km = SphericalKMeans(n_clusters=k, seed=seed, n_init=3, max_iter=25).fit(X)
    return vec, km, X


def main() -> None:
    rows = [json.loads(line) for line in (ROOT / "data" / "jobs_sample.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    categories = [str(r.get("category", "")) for r in rows]
    results = {"n_jobs": len(rows), "k_trials": [], "chosen_k": None}
    best = None
    for k in (6, 8, 10, 13):
        vec, km, X = cluster_jobs(rows, k=k)
        sil = silhouette_cosine(X, km.labels_, sample_size=600)
        pur = purity(km.labels_, categories)
        item = {"k": k, "silhouette": round(sil, 4), "purity": round(pur, 4), "inertia": round(float(km.inertia_), 4)}
        results["k_trials"].append(item)
        print(item)
        if best is None or sil > best[0]:
            best = (sil, k, vec, km, X)
    sil, k, vec, km, X = best
    terms = cluster_terms(km.centroids, vec.vocab, top_n=10)
    sizes = {int(c): int(n) for c, n in zip(*np.unique(km.labels_, return_counts=True))}
    results.update({
        "chosen_k": k,
        "silhouette": round(float(sil), 4),
        "purity": round(purity(km.labels_, categories), 4),
        "cluster_sizes": sizes,
        "cluster_terms": {str(i): terms[i] for i in range(k)},
        "feature_count": len(vec.vocab),
        "method": "TF-IDF(1-2gram) + spherical K-Means++",
        "note": "无监督聚类；purity 只用于解释，不是分类器准确率。",
    })
    (ROOT / "experiments" / "results").mkdir(parents=True, exist_ok=True)
    (ROOT / "experiments" / "results" / "job_cluster_metrics.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ROOT / "models").mkdir(exist_ok=True)
    with (ROOT / "models" / "job_kmeans.pkl").open("wb") as f:
        pickle.dump({"vectorizer": vec, "kmeans": km, "k": k}, f)
    card = {
        "name": "job-kmeans",
        "version": "1.0",
        "method": "TF-IDF + spherical K-Means++",
        "k": k,
        "silhouette": round(float(sil), 4),
        "purity": round(purity(km.labels_, categories), 4),
        "feature_count": len(vec.vocab),
        "cluster_terms": {str(i): terms[i] for i in range(k)},
        "limitations": "无监督聚类，簇不等于岗位族；purity 仅作解释，不作为分类指标。",
    }
    (ROOT / "models" / "job_cluster_card.json").write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    # 每条岗位的簇号，便于后端/报告分析
    with (ROOT / "data" / "job_clusters.csv").open("w", encoding="utf-8") as f:
        f.write("job_id,title,category,cluster\n")
        for r, c in zip(rows, km.labels_):
            title = str(r.get("title", "")).replace(",", "，")
            f.write(f"{r.get('job_id','')},{title},{r.get('category','')},{int(c)}\n")
    print(json.dumps({k: results[k] for k in ("chosen_k", "silhouette", "purity", "cluster_sizes")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
