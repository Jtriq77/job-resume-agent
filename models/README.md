# 模型文件

- `family_clf.pkl`：13 类岗位族分类器（TF-IDF + 多项式 NB）；
- `job_kmeans.pkl`：岗位聚类（TF-IDF + spherical K-Means++）；
- `job_ranker.json`：7 维特征 + 逻辑回归排序器权重；
- `*_card.json`：模型卡片与指标摘要。

指标见 `experiments/results/`；复现命令见 `docs/ML_MODULES.md`。
