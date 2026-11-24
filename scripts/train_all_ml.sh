#!/usr/bin/env bash
set -euo pipefail
export PYTHONHASHSEED=0
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON_BIN:-python3}"
if ! "$PY" -c "import numpy" >/dev/null 2>&1; then
  echo "当前 Python 没有 numpy；请用 PYTHON_BIN=/path/to/python bash scripts/train_all_ml.sh" >&2
  exit 1
fi
cd "$ROOT"
"$PY" scripts/train_family_clf.py
"$PY" scripts/train_job_cluster.py
"$PY" scripts/build_ranker_pairs.py
"$PY" scripts/train_ranker.py
"$PY" scripts/ml_analyze.py
