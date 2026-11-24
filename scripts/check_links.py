"""链接核验：把岗位深链/公司主页分级为 ok / login_required / dead / unknown。

用法：
    python scripts/check_links.py --input data/jobs_linked.jsonl --out data/link_status.csv

说明：
- 只做公开页面的可访问性检查，不登录、不绕过验证码；
- 很多招聘站在 HEAD 请求上返回 405/403，脚本会回退到 GET（只读前 64KB）；
- 结果不是“可投保证”，只是演示前的健康检查。
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
LOGIN_HINTS = ("login", "signin", "sign-in", "passport", "auth", "sso", "account")


def classify(url: str, code: int | None, final_url: str, text: str, error: str | None) -> str:
    if error:
        return "unknown"
    if code in (401, 403):
        return "login_required"
    if code in (404, 410):
        return "dead"
    if code and 200 <= code < 300:
        low = (final_url or url).lower()
        if any(h in low for h in LOGIN_HINTS):
            return "login_required"
        # 页面很短且出现登录字样，通常是被拦截
        if len(text) < 1500 and ("登录" in text or "扫码" in text):
            return "login_required"
        return "ok"
    if code and 300 <= code < 400:
        return "unknown"
    return "unknown"


def fetch(url: str, timeout: int = 12) -> tuple[int | None, str, str, str, str | None]:
    headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
    try:
        resp = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
        if resp.status_code in (405, 403, 400) or resp.status_code >= 500:
            raise requests.RequestException("head not usable")
        text = ""
    except requests.RequestException:
        try:
            resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
            text = ""
            for chunk in resp.iter_content(chunk_size=8192, decode_unicode=False):
                text += chunk.decode("utf-8", errors="ignore")
                if len(text) >= 65536:
                    break
        except requests.RequestException as exc:
            return None, url, "", "", str(exc)
    title = ""
    try:
        title = (BeautifulSoup(text, "html.parser").title.string or "").strip() if text else ""
    except Exception:  # noqa: BLE001
        title = ""
    return resp.status_code, resp.url, text[:65536], title, None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/jobs_linked.jsonl")
    ap.add_argument("--out", default="data/link_status.csv")
    ap.add_argument("--timeout", type=int, default=12)
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        raise SystemExit(f"输入不存在：{src}")

    rows = []
    for line in src.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        job = json.loads(line)
        url = job.get("url") or job.get("career_url")
        if not url:
            rows.append({"job_id": job.get("job_id", ""), "url": "", "status": "unknown",
                         "http_code": "", "final_url": "", "title": "", "checked_at": "", "error": "no_url"})
            continue
        code, final_url, text, title, error = fetch(url, args.timeout)
        status = classify(url, code, final_url, text, error)
        rows.append({
            "job_id": job.get("job_id", ""),
            "url": url,
            "status": status,
            "http_code": code or "",
            "final_url": final_url,
            "title": title,
            "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "error": error or "",
        })
        print(f"{job.get('job_id','?'):>10}  {status:<15} {code}  {url}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["job_id", "url", "status", "http_code", "final_url", "title", "checked_at", "error"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n写入 {out}，共 {len(rows)} 条")


if __name__ == "__main__":
    main()
