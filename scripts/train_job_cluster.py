"""训练岗位聚类模型：TF-IDF + spherical K-Means++。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.job_cluster import main  # noqa: E402

if __name__ == "__main__":
    main()
