#!/usr/bin/env bash
# 下载 job_radar 数据快照（约 200MB 压缩 / 860MB 解压）。
# 用法：bash scripts/download_data.sh
# 说明：只下载公开索引数据；内容版权归原发布方，仅课程研究使用。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RAW="$ROOT/data/_raw_jobradar"
mkdir -p "$RAW"

BASE="https://github.com/lijiaqi-AI-Product-Manager/job_radar/releases/download/data-latest"
# GitHub 直连不稳时用镜像；如镜像失效，改回 BASE 官方地址
MIRROR="${MIRROR:-https://gh-proxy.com/}"

download() {
  local name="$1"
  if [[ -f "$RAW/$name" ]]; then
    echo "[skip] $RAW/$name 已存在"
    return
  fi
  echo "[get] $name"
  curl -L --fail --retry 3 --max-time 1800 -o "$RAW/$name" "$MIRROR$BASE/$name"
}

download jobs.db.gz
download jd_text.db.gz

for f in jobs.db jd_text.db; do
  if [[ ! -f "$RAW/$f" ]]; then
    echo "[unzip] $f"
    gunzip -k "$RAW/$f.gz"
  fi
done

echo "完成：$RAW"
ls -lh "$RAW"/jobs.db "$RAW"/jd_text.db
