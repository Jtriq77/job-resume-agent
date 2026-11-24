"""纯 numpy 实现的 TF-IDF + 多项式朴素贝叶斯文本分类器。

为什么不用 sklearn：
- 当前 macOS 沙箱对第三方编译扩展有代码签名限制，sklearn 轮子加载失败；
- 自己实现后，特征、idf、类条件概率、预测分数都可解释，报告里更好写；
- 3,000–5,000 条、13 类文本，纯 numpy 足够快。

特征：
- 中文 1–3 字符 n-gram；
- 英文/数字 token；
- 标题重复两次，提升标题权重。
"""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np

URL_RE = re.compile(r"https?://\S+|www\.\S+")
EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
EN_RE = re.compile(r"[a-z0-9+#.]+")
ZH_RE = re.compile(r"[\u4e00-\u9fff]+")
PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff+#.]+")


def normalize(text: str) -> str:
    text = (text or "").lower()
    text = URL_RE.sub(" ", text)
    text = EMAIL_RE.sub(" ", text)
    text = PUNCT_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def features(text: str, n_min: int = 1, n_max: int = 3) -> list[str]:
    text = normalize(text)
    out: list[str] = []
    # 中文连续片段 → 字符 n-gram
    for seq in ZH_RE.findall(text):
        for n in range(n_min, n_max + 1):
            if len(seq) < n:
                continue
            out.extend(seq[i:i + n] for i in range(len(seq) - n + 1))
    # 英文/数字 token
    out.extend(EN_RE.findall(text))
    return out


class TfidfNB:
    def __init__(self, max_features: int = 30000, n_min: int = 1, n_max: int = 3, alpha: float = 0.3):
        self.max_features = max_features
        self.n_min = n_min
        self.n_max = n_max
        self.alpha = alpha
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.classes: list[str] = []
        self.log_prior: np.ndarray | None = None
        self.log_prob: np.ndarray | None = None

    def _doc_features(self, title: str, body: str) -> list[str]:
        # 标题重复两次，提升权重
        return features(title + " " + title + " " + body, self.n_min, self.n_max)

    def fit(self, rows: Iterable[dict], title_key: str = "title", body_key: str = "jd_text", label_key: str = "category"):
        rows = list(rows)
        df: Counter[str] = Counter()
        tokenized: list[list[str]] = []
        labels: list[str] = []
        for r in rows:
            toks = self._doc_features(str(r.get(title_key, "")), str(r.get(body_key, "")))
            tokenized.append(toks)
            labels.append(str(r[label_key]))
            df.update(set(toks))
        # 只保留至少在 2 篇文档出现的特征，再按 df 截断
        vocab_terms = [t for t, c in df.most_common() if c >= 2][: self.max_features]
        self.vocab = {t: i for i, t in enumerate(vocab_terms)}
        self.classes = sorted(set(labels))
        cls_idx = {c: i for i, c in enumerate(self.classes)}
        V = len(self.vocab)
        N = len(rows)
        self.idf = np.array(
            [math.log((1 + N) / (1 + df[t])) + 1.0 for t in vocab_terms], dtype=np.float64
        )

        class_sums = np.zeros((len(self.classes), V), dtype=np.float64)
        class_totals = np.zeros(len(self.classes), dtype=np.float64)
        class_counts = np.zeros(len(self.classes), dtype=np.float64)
        for toks, label in zip(tokenized, labels):
            vec = self._vectorize_tokens(toks)
            ci = cls_idx[label]
            class_counts[ci] += 1
            if vec:
                idx = np.fromiter(vec.keys(), dtype=np.int64)
                val = np.fromiter(vec.values(), dtype=np.float64)
                class_sums[ci, idx] += val
                class_totals[ci] += val.sum()
        self.log_prior = np.log(class_counts / class_counts.sum())
        self.log_prob = np.log(
            (class_sums + self.alpha) / (class_totals[:, None] + self.alpha * max(1, V))
        )
        return self

    def _vectorize_tokens(self, toks: list[str]) -> dict[int, float]:
        counts: Counter[int] = Counter()
        for t in toks:
            j = self.vocab.get(t)
            if j is not None:
                counts[j] += 1
        if not counts:
            return {}
        # sublinear tf
        vec = {j: 1.0 + math.log(c) for j, c in counts.items()}
        # l2 normalize
        norm = math.sqrt(sum((v * self.idf[j]) ** 2 for j, v in vec.items()))
        if norm == 0:
            return {}
        return {j: (v * self.idf[j]) / norm for j, v in vec.items()}

    def vectorize(self, title: str, body: str) -> dict[int, float]:
        return self._vectorize_tokens(self._doc_features(title, body))

    def decision_function(self, vec: dict[int, float]) -> np.ndarray:
        scores = self.log_prior.copy()
        for j, w in vec.items():
            scores += w * self.log_prob[:, j]
        return scores

    def predict_one(self, title: str, body: str) -> tuple[str, float, dict[str, float]]:
        scores = self.decision_function(self.vectorize(title, body))
        probs = softmax(scores)
        i = int(np.argmax(probs))
        return self.classes[i], float(probs[i]), {c: float(p) for c, p in zip(self.classes, probs)}

    def predict(self, rows: Iterable[dict], title_key: str = "title", body_key: str = "jd_text") -> list[str]:
        out = []
        for r in rows:
            scores = self.decision_function(self.vectorize(str(r.get(title_key, "")), str(r.get(body_key, ""))))
            out.append(self.classes[int(np.argmax(scores))])
        return out

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str | Path) -> "TfidfNB":
        with Path(path).open("rb") as f:
            return pickle.load(f)


def softmax(scores: np.ndarray) -> np.ndarray:
    z = scores - np.max(scores)
    e = np.exp(z)
    return e / e.sum()


def prf(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict:
    per = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[label] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4), "support": tp + fn}
    macro = sum(v["f1"] for v in per.values()) / max(1, len(per))
    total = len(y_true)
    weighted = sum(v["f1"] * v["support"] for v in per.values()) / max(1, total)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(1, total)
    return {
        "accuracy": round(acc, 4),
        "macro_f1": round(macro, 4),
        "weighted_f1": round(weighted, 4),
        "per_class": per,
    }


def confusion(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, dict[str, int]]:
    mat = {a: {b: 0 for b in labels} for a in labels}
    for t, p in zip(y_true, y_pred):
        if t in mat and p in mat[t]:
            mat[t][p] += 1
    return mat


def stratified_split(rows: list[dict], label_key: str = "category", test_ratio: float = 0.2, seed: int = 42):
    import random

    by_label: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_label[str(r[label_key])].append(r)
    rng = random.Random(seed)
    train, test = [], []
    for label, items in by_label.items():
        rng.shuffle(items)
        n_test = max(1, int(len(items) * test_ratio))
        test.extend(items[:n_test])
        train.extend(items[n_test:])
    rng.shuffle(train)
    rng.shuffle(test)
    return train, test
