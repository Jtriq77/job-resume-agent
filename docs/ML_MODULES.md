# 机器学习模块：三个知识点与实验证据

> 目标：证明本项目不是“只调 LLM API”，而是有独立实现、可复现实验和误差分析的 ML 后端。

## 0. 总览

| # | 知识点 | 任务 | 模型 | 代码 | 结果文件 |
|---|---|---|---|---|---|
| 1 | 监督分类 / 文本分类 | 岗位族分类（13 类） | TF-IDF + 多项式朴素贝叶斯 | `src/ml/text_clf.py`、`scripts/train_family_clf.py` | `experiments/results/family_clf_metrics.json` |
| 2 | 无监督聚类 | 岗位分群 | TF-IDF + spherical K-Means++ | `src/ml/job_cluster.py`、`scripts/train_job_cluster.py` | `experiments/results/job_cluster_metrics.json` |
| 3 | 特征工程 + 学习排序 | 简历–岗位排序 | L2 逻辑回归（pointwise LTR） | `src/ml/ranker.py`、`scripts/build_ranker_pairs.py`、`scripts/train_ranker.py` | `experiments/results/ranker_metrics.json` |

三个模型都用 numpy 从零实现，不依赖 sklearn；原因是当前 macOS 沙箱对 sklearn 编译扩展有 Team ID 签名限制。这样也便于在报告里写清公式、特征和训练过程。

---

## 1. 岗位族分类：TF-IDF + Multinomial NB

### 特征

- 中文 1–3 字符 n-gram + 英文/数字 token；
- 标题重复两次，提高标题权重；
- TF-IDF：sublinear tf，L2 归一化，`max_features=30000`，`min_df=2`；
- 多项式 NB，`alpha=0.3`。

### 数据与评估

- 3,900 条岗位，13 类 × 300；
- 分层 80/20：3,120 训练 / 780 测试，`seed=42`；
- 指标：Accuracy、Macro-F1、Weighted-F1、逐类 P/R/F1、混淆矩阵。

### 结果

| 配置 | Macro-F1 |
|---|---:|
| 标题 + 正文（主模型） | **0.7602** |
| 只用标题 | 0.9244（标签与标题同源，存在泄漏，不作为泛化结论） |
| 多数类基线 | 0.0110 |

**局限**：标签是 job_radar 的规则职类（银标准），不是人工金标准；需要 300 条人工标注复核，报告不能用 0.760 声称真实业务泛化。

---

## 2. 岗位聚类：TF-IDF + spherical K-Means++

### 方法

- 文本：`title + title + JD 前 1800 字`；
- 特征：中文 1–2-gram + 英文 token，TF-IDF，`max_features=3000`，`min_df=2`；
- 距离：余弦距离；向量 L2 归一化；
- 初始化：K-Means++；
- 更新：簇内均值后重新归一化（spherical K-Means）；
- k 搜索：6 / 8 / 10 / 13，用余弦轮廓系数选 k；
- 解释：簇纯度（用岗位族标签，仅解释，不作为分类指标）。

### 结果

| k | 轮廓系数 | 纯度 | inertia |
|---:|---:|---:|---:|
| 6 | 0.0543 | 0.3115 | 0.5399 |
| 8 | 0.0638 | 0.3826 | 0.5250 |
| 10 | 0.0617 | 0.4641 | 0.5145 |
| 13 | **0.0656** | **0.4564** | 0.5004 |

- 选择 `k=13`；
- 簇规模：208 / 357 / 448 / 137 / 218 / 384 / 103 / 367 / 713 / 339 / 213 / 194 / 219；
- 轮廓系数偏低（0.066）：岗位 JD 用词重叠大、短文本噪声多，簇边界模糊；这是**无监督文本聚类的真实局限**，不是“模型完美”。
- 产物：`models/job_kmeans.pkl`、`data/job_clusters.csv`、`models/job_cluster_card.json`。

### 报告可写的分析

- 为什么 k=13 仍出现 830 条的大簇：泛化型岗位/职能描述重复；
- 聚类不是分类替代品：它没有标签，只能做岗位分群、冷启动和探索；
- 低轮廓系数说明“岗位族”不是自然簇，后续可改用有监督分类或半监督。

---

## 3. 简历–岗位排序：特征工程 + 逻辑回归

### 特征（7 维）

1. `skill_cov`：简历技能在 JD 中的覆盖率；
2. `title_hit`：求职意向与岗位标题的 token 命中率；
3. `text_cos`：简历文本与 JD 的 token 余弦相似度；
4. `city_match`：目标城市是否匹配；
5. `edu_match`：学历是否达到岗位最低要求；
6. `jd_len_norm`：JD 长度归一化；
7. `title_len_norm`：标题长度归一化。

### 模型

- Pointwise 逻辑回归：`P(relevant=1|x)=sigmoid(w·x+b)`；
- L2 正则，梯度下降，`lr=0.1`，`epochs=500`，`l2=1e-3`；
- 训练/测试按 job_id 分桶，避免同一岗位泄漏。

### 数据

- 5 个虚构候选人画像（数据/产品/前端/后端/运营）；
- 每个画像抽 40 条/岗位族，共 2,600 对；
- 弱标签：岗位族命中目标族为 1，否则 0；
- **不是人工相关性标注**，不能当真实业务 NDCG。

### 结果

| 指标 | 逻辑回归 | 技能覆盖基线 |
|---|---:|---:|
| NDCG@5 | **0.8543** | 0.5839 |
| NDCG@10 | **0.8572** | 0.5742 |
| Recall@5 | **0.3320** | 0.0458 |

- `Recall@5` 低是因为每个画像正例远多于 5 个，Top-5 最多只能覆盖 5 个；
- 部分画像（产品/运营）出现 NDCG@5=1.0，是因为测试正例少、Top-5 刚好全中，不能外推；
- 基线在前端/后端画像上为 0，是因为技能字符串与 JD 表述不一致，说明纯字符串覆盖的脆弱性；
- 产物：`data/ranker_pairs.csv`、`models/job_ranker.json`、`experiments/results/ranker_metrics.json`。

### 报告可写的分析

- 特征工程比“技能字符串覆盖”更稳；
- `category_match` 曾作为特征导致 NDCG=1.0 的标签泄漏，已移除；
- 弱标签只能证明“流程可训练、可评估”，不能证明真实用户满意；
- 下一步：100–150 对人工相关性标注，重跑 NDCG/Recall。

---

## 4. 复现命令

```bash
cd "/Users/jiangyingying/Desktop/机器学习大作业"
PY="/Users/jiangyingying/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3"

# 1) 分类
$PY scripts/train_family_clf.py

# 2) 聚类
$PY scripts/train_job_cluster.py

# 3) 排序
$PY scripts/build_ranker_pairs.py
$PY scripts/train_ranker.py
```

所有指标写入 `experiments/results/*.json`，模型写入 `models/`。

---

## 5. 与 Agent 的关系

- **岗位族分类**：后端判断岗位属于产品/技术/运营等，用于岗位卡片和方向解释；
- **岗位聚类**：后端对 3,900 条岗位做无监督分群，输出 `data/job_clusters.csv`，用于冷启动/分群分析；
- **排序器**：后端学习简历–岗位匹配，替代纯技能覆盖基线；当前是实验模型，前端未改。

> 前端页面没有为了 ML 增加新控件；ML 改动集中在 `src/ml/`、`scripts/`、`models/`、`experiments/`。
