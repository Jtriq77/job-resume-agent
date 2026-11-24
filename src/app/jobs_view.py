"""三档岗位与投递动作：大厂/中厂/小厂、链接、打招呼语、标记已投、漏斗。"""

from __future__ import annotations

import csv
import html
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ml.baseline_ranker import SkillBaselineRanker  # noqa: E402
from src.app.trace_panel import trace_once, trace_record  # noqa: E402

TIERS = [("冲刺 · 大厂", "大厂"), ("匹配 · 中厂", "中厂"), ("保底 · 小厂", "小厂")]
APPS = ROOT / "data" / "applications.csv"
APP_FIELDS = ["app_id", "job_id", "company", "title", "tier", "status", "applied_at", "channel", "resume_version", "follow_up_at", "note"]


def load_jobs() -> list[dict]:
    path = ROOT / "data" / "jobs_linked.jsonl"
    if not path.exists():
        return []
    jobs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    status_path = ROOT / "data" / "link_status.csv"
    status = {}
    if status_path.exists():
        with status_path.open(encoding="utf-8") as f:
            status = {row["job_id"]: row for row in csv.DictReader(f)}
    for j in jobs:
        row = status.get(j["job_id"], {})
        j["link_status"] = row.get("status", "unknown")
        j["link_checked"] = row.get("checked_at", "")
        j["link_title"] = row.get("title", "")
    return jobs


def load_apps() -> list[dict]:
    if not APPS.exists():
        return []
    with APPS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_app(row: dict) -> None:
    APPS.parent.mkdir(parents=True, exist_ok=True)
    exists = APPS.exists()
    with APPS.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=APP_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def channel_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "shixiseng" in host:
        return "实习僧"
    if "zhiye" in host or "hotjob" in host or "feishu" in host:
        return "公司招聘系统"
    return host or "官网"


def greeting(job: dict, name: str = "同学") -> str:
    return (
        f"您好，我是{name}，对贵司「{job.get('title','')}」岗位很感兴趣。"
        f"我有 {job.get('matched_skills_text','SQL/Python/数据分析')} 相关经历，"
        f"与岗位要求的 {job.get('category','')} 方向匹配，期待有机会进一步沟通。"
    )


def score_jobs(jobs: list[dict], city: str, families: list[str]) -> list[dict]:
    profile = {
        "skills": ["SQL", "Python", "Tableau", "数据分析", "AB 测试"],
        "job_intent": families or ["数据分析", "产品运营"],
        "target_cities": [city] if city else [],
        "degree": "本科",
    }
    ranker = SkillBaselineRanker()
    out = []
    for j in jobs:
        s = ranker.score(profile, j)
        matched = "、".join(s["matched_skills"]) or "暂无"
        j = {**j, **s, "matched_skills_text": matched}
        out.append(j)
    out.sort(key=lambda x: x["score"], reverse=True)
    return out


def render_job_card(job: dict, idx: int) -> None:
    url = job.get("url") or ""
    fallback = job.get("career_url") or ""
    status = job.get("link_status", "unknown")
    with st.container(border=True):
        st.markdown(f"**{job.get('title','')}**")
        st.caption(
            f"{job.get('company','')} · {'/'.join(job.get('cities', [])) or '城市未标注'} · "
            f"{job.get('category','')}/{job.get('subcategory','')} · {job.get('recruit_type','')}"
        )
        c1, c2 = st.columns([0.7, 0.3])
        with c1:
            st.progress(min(1.0, float(job.get("score", 0))))
        with c2:
            st.metric("匹配分", f"{float(job.get('score', 0)):.2f}")
        st.caption(f"匹配：{job.get('matched_skills_text','暂无')} ｜ 缺失：{'、'.join(job.get('missing_skills', [])[:4]) or '无'}")
        if status == "login_required":
            st.warning("这个链接需要登录或 App 打开；可以先去公司主页。")
        elif status == "dead":
            st.error("这个链接已失效，可以先去公司主页。")
        elif status == "unknown":
            st.caption("这个链接还没检查，使用前请手动确认。")

        cols = st.columns(4)
        with cols[0]:
            if url:
                st.link_button("去投递", url, use_container_width=True)
            elif fallback:
                st.link_button("去公司主页", fallback, use_container_width=True)
        with cols[1]:
            if st.button("标记已投", key=f"apply_{job['job_id']}_{idx}", use_container_width=True):
                now = datetime.now().astimezone()
                append_app({
                    "app_id": f"a{now.strftime('%Y%m%d%H%M%S')}",
                    "job_id": job["job_id"],
                    "company": job.get("company", ""),
                    "title": job.get("title", ""),
                    "tier": job.get("tier", ""),
                    "status": "已投",
                    "applied_at": now.isoformat(timespec="seconds"),
                    "channel": channel_of(url or fallback),
                    "resume_version": "base（模板待接入）",
                    "follow_up_at": (now + timedelta(days=7)).isoformat(timespec="seconds"),
                    "note": "",
                })
                trace_record(
                    "jobs", "apply", "标记已投",
                    tool="applications.csv",
                    why="把你的这次投递记下来，7 天后提醒你跟进；不会自动替你提交。",
                    input_summary=f"{job.get('company','')} · {job.get('title','')}",
                    output_summary="已记录，待跟进",
                )
                st.success("已记录：7 天后提醒跟进")
        with cols[2]:
            if st.button("打招呼语", key=f"greet_{job['job_id']}_{idx}", use_container_width=True):
                st.session_state[f"greet_show_{job['job_id']}"] = True
        with cols[3]:
            st.button("定制简历", key=f"tailor_{job['job_id']}_{idx}", disabled=True, use_container_width=True)
        if st.session_state.get(f"greet_show_{job['job_id']}"):
            st.code(greeting(job), language="text")
            st.caption("点代码块右上角复制；正式版会按平台字数限制生成不同版本。")
        if fallback and status in ("login_required", "dead"):
            st.link_button("公司招聘主页（兜底）", fallback)


def render_jobs_tab(city: str, families: list[str]) -> None:
    jobs = load_jobs()
    if not jobs:
        st.info("岗位库尚未生成。先运行 `python scripts/build_linked_set.py`。")
        return
    trace_once(
        "jobs", "load", "读取岗位",
        tool="jobs_linked.jsonl",
        why="读取大厂、中厂、小厂的岗位，并检查每个岗位链接能不能打开。",
        output_summary=f"{len(jobs)} 条岗位",
    )
    scored = score_jobs(jobs, city, families)
    trace_once(
        "jobs", "score", "推荐岗位",
        tool="SkillBaselineRanker",
        why="根据你的技能、岗位标题、城市和学历，给每个岗位算一个匹配分。",
        input_summary=f"城市：{city}；方向：{'、'.join(families)}",
        output_summary=f"完成 {len(scored)} 条排序",
    )
    trace_once(
        "jobs", "links", "检查链接",
        tool="link_status.csv",
        why="检查岗位链接：哪些能直接打开，哪些需要登录，哪些已经失效。",
        output_summary=f"ok {sum(1 for j in scored if j['link_status']=='ok')} / login {sum(1 for j in scored if j['link_status']=='login_required')} / dead {sum(1 for j in scored if j['link_status']=='dead')}",
    )
    tabs = st.tabs([t[0] for t in TIERS])
    for tab, (label, tier) in zip(tabs, TIERS):
        with tab:
            subset = [j for j in scored if j.get("tier") == tier][:5]
            if not subset:
                st.info(f"当前筛选下没有{label}岗位。")
                continue
            for i, job in enumerate(subset):
                render_job_card(job, i)


def render_tracking_tab() -> None:
    apps = load_apps()
    st.subheader("投递追踪")
    trace_once(
        "tracking", "load", "读取投递记录",
        tool="applications.csv",
        why="读取你的投递记录，算出已投、待跟进、面试和回复率。",
        output_summary=f"{len(apps)} 条投递记录",
    )
    if not apps:
        st.info("还没有投递记录。去「三档岗位」点「标记已投」即可。")
        return
    now = datetime.now().astimezone()
    due = []
    for a in apps:
        try:
            fu = datetime.fromisoformat(a.get("follow_up_at", ""))
            if fu <= now and a.get("status") == "已投":
                due.append(a)
        except Exception:  # noqa: BLE001
            pass
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("已投", len(apps))
    c2.metric("待跟进", len(due))
    c3.metric("面试", sum(1 for a in apps if a.get("status") == "面试"))
    c4.metric("回复率", f"{sum(1 for a in apps if a.get('status') in ('笔试','面试','Offer'))/len(apps):.0%}")
    if due:
        st.warning(f"有 {len(due)} 条已投超过 7 天，建议跟进：" + "、".join(a["company"] for a in due[:5]))
    cols = ["applied_at", "company", "title", "tier", "status", "channel", "follow_up_at"]
    head = "".join(f"<th style='text-align:left;padding:6px 10px;border-bottom:1px solid #e2e8f0'>{c}</th>" for c in cols)
    body = ""
    for a in apps:
        tds = "".join(
            f"<td style='padding:6px 10px;border-bottom:1px solid #f1f5f9'>{html.escape(str(a.get(c, '')))}</td>"
            for c in cols
        )
        body += f"<tr>{tds}</tr>"
    st.markdown(
        f"<div style='overflow-x:auto'><table style='width:100%;border-collapse:collapse;font-size:0.85rem'>"
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    with st.expander("更新状态"):
        options = {f"{a['company']} · {a['title']}": a["app_id"] for a in apps}
        choice = st.selectbox("选择记录", list(options.keys()))
        status = st.selectbox("新状态", ["已投", "笔试", "面试", "拒绝", "Offer"])
        if st.button("保存状态"):
            rows = load_apps()
            for r in rows:
                if r["app_id"] == options[choice]:
                    r["status"] = status
            with APPS.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=APP_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
            trace_record(
                "tracking", "update_status", "更新投递状态",
                tool="applications.csv",
                why="把你选择的新状态保存到投递记录里。",
                output_summary=f"{choice} → {status}",
            )
            st.success("已更新")
            st.rerun()
