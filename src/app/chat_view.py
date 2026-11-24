"""对话式信息采集：一段话 → 抽取画像 → 追问缺失 → 生成简历。"""

from __future__ import annotations

import hashlib
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.polish import polish_profile  # noqa: E402
from src.agent.direction import recommend_directions  # noqa: E402
from src.agent.tailor import tailor_profile  # noqa: E402
from src.agent.profile_extract import (  # noqa: E402
    apply_supplement,
    build_contact,
    extract,
    merge,
    missing_required,
    next_question,
    summary,
    _blank,
    _dates,
)
from src.app.intake_view import PROFILE, _generate, _docx_python  # noqa: E402
from src.app.trace_panel import trace_once, trace_record, trace_step  # noqa: E402

GREETING = """你好，我是简历助手。你可以把个人信息**一段话**发我，我会整理成：
姓名、年龄、政治面貌、手机/邮箱、学校/专业、实习、项目/竞赛、技能。

比如：
> 我叫李同学，22岁，共青团员，上海，手机 13800000000，邮箱 li@example.com。某211大学信息管理与信息系统专业本科，2026 届。2025.03-2025.08 在字节跳动做数据分析实习，负责 SQL 取数和 A/B 测试。2025.09 做了用户流失预测项目，用 Python，AUC 0.81。技能：SQL、Python、Tableau。

缺的我会继续问；信息够了先看「方向推荐」，选一个方向后我再把每段经历写细。"""


def _init() -> None:
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [{"role": "assistant", "content": GREETING}]
    if "chat_profile" not in st.session_state:
        restored = False
        if PROFILE.exists():
            try:
                data = json.loads(PROFILE.read_text(encoding="utf-8"))
                base = _blank()
                base.update(data)
                st.session_state.chat_profile = base
                restored = True
            except Exception:  # noqa: BLE001
                st.session_state.chat_profile = _blank()
        else:
            st.session_state.chat_profile = _blank()
        if restored:
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "我保留了你上次的信息；你可以继续补充，已有的教育/实习/项目/技能不会被覆盖。",
            })
    if "chat_generated" not in st.session_state:
        st.session_state.chat_generated = ""
    if "selected_direction" not in st.session_state:
        st.session_state.selected_direction = ""
    if "chat_generated_hash" not in st.session_state:
        st.session_state.chat_generated_hash = ""


def _profile_hash(profile: dict, direction: str) -> str:
    raw = json.dumps({"profile": profile, "direction": direction}, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _handle(text: str) -> None:
    old_generated = st.session_state.get("chat_generated")
    had_generated = bool(old_generated)
    st.session_state.chat_messages.append({"role": "user", "content": text})
    profile = st.session_state.chat_profile
    with trace_step(
        "chat", "extract", "整理信息",
        tool="resume-section-extractor",
        why="把你发来的一段话分成教育、实习、校园与项目、技能四块；没提到的先留空，后面继续问你。",
        input_summary=text[:160],
    ) as step:
        new, _source = extract(text)
        step.finish(
            output_summary=f"教育 {len(new.get('educations', []))} / 实习 {len(new.get('internships', []))} / 校园 {len(new.get('campus', []))} / 技能 {len(new.get('skills', []))}",
            detail={"source": _source, "warnings": new.get("_warnings", [])},
        )
    with trace_step(
        "chat", "merge", "补充信息",
        tool="merge + supplement",
        why="把这次补充的内容接在已有信息后面，不覆盖原来的经历；奖学金、竞赛和技能会补到对应位置。",
        input_summary="补充到已有信息",
    ) as step:
        profile = merge(profile, new)
        profile, added = apply_supplement(profile, text)
        step.finish(
            output_summary=f"教育 {len(profile.get('educations', []))} / 实习 {len(profile.get('internships', []))} / 校园 {len(profile.get('campus', []))} / 技能 {len(profile.get('skills', []))}",
            detail={"added": added},
        )

    if any(k in text for k in ["没有实习", "无实习", "没实习"]):
        profile["_no_internship"] = True
    if any(k in text for k in ["没有项目", "无项目", "没项目", "没有竞赛", "无竞赛"]):
        profile["_no_campus"] = True
    if text.strip() in ("没有", "都没有", "无"):
        if not profile.get("internships"):
            profile["_no_internship"] = True
        elif not profile.get("campus"):
            profile["_no_campus"] = True

    if any(k in text for k in ["不记得", "忘了", "不确定", "没有时间", "记不清"]):
        profile["_skip_dates"] = True

    # 用户只回一个日期区间时，补到第一段缺日期的实习/项目上
    ds = _dates(text)
    if len(ds) >= 2 and len(text.strip()) <= 40:
        for it in profile.get("internships", []):
            if not it.get("date"):
                it["date"] = f"{ds[0]}-{ds[1]}"
                break
        else:
            for it in profile.get("campus", []):
                if not it.get("date"):
                    it["date"] = f"{ds[0]}-{ds[1]}"
                    break

    # 用户可能只回「数据分析」这种短答案，补一下求职意向
    if not profile.get("job_intent") and len(text.strip()) <= 30 and any(
        k in text for k in ["数据分析", "产品", "运营", "算法", "开发", "商业分析", "用户增长"]
    ):
        profile["job_intent"] = text.strip()

    profile["contact"] = build_contact(profile)
    st.session_state.chat_profile = profile
    # 画像一变，旧简历立即失效，避免继续下载旧文件
    st.session_state.chat_generated = ""
    st.session_state.chat_generated_hash = ""
    if old_generated:
        try:
            Path(old_generated).unlink(missing_ok=True)
        except Exception:  # noqa: BLE001
            pass
    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    reply = ("我记下了：\n\n" + summary(profile)
             + "\n\n" + next_question(profile)
             + "\n\n生成时我会把口语整理成简历表达（只改写、不新增数字），下面可以看对比。")
    if added:
        reply += "\n\n已补充：" + "、".join(dict.fromkeys(added))
    if had_generated:
        reply += "\n\n信息已更新，之前生成的简历已隐藏；请重新生成，确保新增经历进入简历。"
    st.session_state.chat_messages.append({"role": "assistant", "content": reply})


def _generate_tailored(profile: dict, direction: str) -> tuple[bool, str]:
    py = _docx_python()
    if not py:
        return False, "找不到可 import docx 的 Python 解释器"
    path = ROOT / "data" / "profile_tailored.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    name = profile.get("name") or "我的简历"
    out = ROOT / "data" / "output" / f"简历_{name}_{direction}.docx"
    r = subprocess.run(
        [py, str(ROOT / "scripts" / "build_resume_from_profile.py"),
         "--profile", str(path), "--out", str(out)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-800:]
    return True, str(out)


def _apply_edited_json(text: str) -> None:
    try:
        data = json.loads(text)
    except Exception as exc:  # noqa: BLE001
        st.error(f"内容格式不对：{exc}")
        return
    base = _blank()
    base.update(data)
    base["contact"] = build_contact(base)
    st.session_state.chat_profile = base
    st.session_state.chat_messages.append({"role": "assistant", "content": "已按你修改的信息更新。"})
    st.rerun()


def render_chat_tab() -> None:
    _init()
    st.subheader("对话采集")
    has_key = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))
    st.caption("不用填表：把姓名、学校、专业、实习、项目、技能一段话发我；我会整理并追问缺失项。")
    st.caption("信息整理：已就绪" if has_key else "信息整理：基础模式")

    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    with st.form("chat_form", clear_on_submit=True):
        text = st.text_area(
            "把你的信息发给我",
            height=130,
            placeholder="我叫……，手机……，邮箱……，某大学某专业本科，2026 届；在……实习，做过……项目；技能……",
        )
        send = st.form_submit_button("发送", type="primary", use_container_width=True)

    if send and text.strip():
        _handle(text.strip())
        st.rerun()

    profile = st.session_state.chat_profile
    if not any([profile.get("name"), profile.get("phone"), profile.get("educations")]):
        return

    st.markdown("---")
    st.markdown("### 我整理的信息")
    st.text(summary(profile))

    warnings = profile.get("_warnings") or []
    if warnings:
        with st.expander(f"⚠️ 核对提醒：{len(warnings)} 个数字/名称在原文没找到", expanded=False):
            for w in warnings:
                st.markdown(f"- {w}")
            st.caption("这些内容可能是自动补的，生成前请确认；确认无误可忽略，或改原文后重新整理。")

    st.markdown("### 简历内容预览")
    st.caption("生成简历时，只会往这四个板块里填；多出来的信息会归到最接近的一段，不会新开第五段。")
    with st.expander("1. 教育背景", expanded=True):
        edus = profile.get("educations", [])
        if not edus:
            st.caption("暂无，继续补充学校/专业/时间。")
        for e in edus:
            st.markdown(f"**{e.get('school','')}｜{e.get('major','')}｜{e.get('degree','')}**  \n{e.get('date','')}")
            if e.get("gpa"):
                st.caption(f"GPA/排名：{e['gpa']}")
            if e.get("extra"):
                st.caption(f"荣誉/补充：{e['extra']}")
            if e.get("courses"):
                st.caption(f"课程：{e['courses']}")
    with st.expander("2. 实习经历", expanded=True):
        ints = profile.get("internships", [])
        if not ints:
            st.caption("暂无实习；没有就回「没有实习」，会用项目/校园经历补。")
        for it in ints:
            st.markdown(f"**{it.get('company','')}｜{it.get('dept','')}｜{it.get('role','')}**  \n{it.get('date','')}")
            for b in it.get("bullets", []):
                st.markdown(b if profile.get("_format") == "paragraph" else f"- {b}")
    with st.expander("3. 校园与项目经历", expanded=True):
        camps = profile.get("campus", [])
        if not camps:
            st.caption("暂无项目/校园经历；有就按「时间 + 名称 + 你做了什么 + 结果」补一段。")
        for it in camps:
            st.markdown(f"**{it.get('org','')}｜{it.get('role','')}**  \n{it.get('date','')}")
            for b in it.get("bullets", []):
                st.markdown(b if profile.get("_format") == "paragraph" else f"- {b}")
    with st.expander("4. 技能特长", expanded=True):
        skills = profile.get("skills", [])
        if not skills:
            st.caption("暂无技能；补充语言、工具、证书。")
        for sk in skills:
            st.markdown(f"- {sk}")
    with st.expander("预览：原文 → 简历表达（只改写，不新增数字）"):
        polished, changes = polish_profile(profile)
        if not changes:
            st.caption("还没有实习/项目 bullet；补充后这里会显示改写对比。")
        else:
            rows = ""
            for ch in changes:
                before = html.escape(ch["before"] or "—")
                after = html.escape(ch["after"] or "—")
                rows += (
                    "<tr>"
                    f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;color:#64748b'>{html.escape(ch['section'])} · {html.escape(ch['org'])}</td>"
                    f"<td style='padding:8px;border-bottom:1px solid #e2e8f0'>{before}</td>"
                    f"<td style='padding:8px;border-bottom:1px solid #e2e8f0;color:#0f172a'>{after}</td>"
                    "</tr>"
                )
            st.markdown(
                "<table style='width:100%;border-collapse:collapse;font-size:0.82rem'>"
                "<thead><tr><th style='text-align:left;padding:8px'>段落</th>"
                "<th style='text-align:left;padding:8px'>你原话</th>"
                "<th style='text-align:left;padding:8px'>简历表达</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>",
                unsafe_allow_html=True,
            )
            st.caption("如果哪条改得不对，展开下面的内容改原文，或切到「📝 表单填写」修正；生成时会重新整理。")

    with st.expander("查看 / 修改信息"):
        raw = st.text_area("信息内容", json.dumps(profile, ensure_ascii=False, indent=2), height=260)
        if st.button("应用修改"):
            _apply_edited_json(raw)

    st.markdown("### 方向推荐")
    st.caption("第一次先看方向：根据你现在的技能和经历，给 3 个大致契合的方向；选定后再把每段经历写细。不选也可以生成基础版。")
    directions = recommend_directions(profile)
    trace_once(
        "chat", "direction", "方向推荐",
        tool="direction.recommend_directions",
        why="根据你已经有的技能和经历，挑出 3 个比较适合的方向。",
        output_summary="、".join(d["name"] for d in directions),
    )
    cols = st.columns(3)
    for i, d in enumerate(directions):
        with cols[i]:
            st.markdown(f"**{d['name']}**")
            st.progress(min(1.0, float(d.get("score", 0))))
            st.caption(d.get("reason", ""))
            if d.get("missing"):
                st.caption("建议补充：" + "、".join(d["missing"][:3]))
            if st.button("选这个方向", key=f"pick_dir_{d['name']}", use_container_width=True):
                st.session_state.selected_direction = d["name"]
                trace_record("chat", "pick_direction", "选择方向", tool="human_gate",
                             why="你选定方向后，才开始按这个方向整理简历。", output_summary=d["name"])
                st.rerun()

    selected = st.session_state.get("selected_direction", "")
    if selected:
        st.success(f"已选方向：**{selected}**。生成时会按这个方向重写每段实习/项目/校园经历。")

    missing = missing_required(profile)
    c1, c2 = st.columns([0.62, 0.38])
    with c1:
        if missing:
            st.warning("还差必填项：" + "、".join(missing) + "。继续在对话框里补一句即可。")
        else:
            label = f"按「{selected}」方向定制简历" if selected else "生成基础版简历（先不定向）"
            if st.button(label, type="primary", use_container_width=True):
                if selected:
                    with st.spinner(f"正在按「{selected}」方向整理实习 / 项目 / 校园经历…"):
                        with trace_step(
                            "chat", "tailor", f"按「{selected}」方向整理",
                            tool="resume-direction-tailor",
                            why="把每段实习、项目和校园经历写成一段完整的话，写清你做了什么、怎么做、结果怎样；不编造没有的经历。",
                            input_summary=f"方向：{selected}",
                        ) as step:
                            tailored, source, warns = tailor_profile(profile, selected)
                            step.finish(
                                output_summary=f"实习 {len(tailored.get('internships', []))} 段 / 校园 {len(tailored.get('campus', []))} 段",
                                detail={"source": source, "warnings": warns},
                            )
                        with trace_step(
                            "chat", "docx", "生成简历",
                            tool="docx_template",
                            why="把整理好的内容放进简历模板；经历超过两段时，自动增加对应的段落。",
                            input_summary=selected,
                        ) as step:
                            ok, msg = _generate_tailored(tailored, selected)
                            step.finish(
                                output_summary="已生成" if ok else msg,
                                detail={"file": msg},
                                status="done" if ok else "error",
                            )
                    if ok:
                        st.session_state.chat_generated = msg
                        st.session_state.chat_generated_hash = _profile_hash(profile, selected)
                        st.session_state.chat_tailor_source = source
                        st.session_state.chat_tailor_warnings = warns
                        st.session_state.chat_messages.append({
                            "role": "assistant",
                            "content": f"已按「{selected}」方向生成简历，每段经历都写成一整段连续文字，包含背景/职责/技术/结果。可以下载，也可以继续补充细节。",
                        })
                        st.rerun()
                    else:
                        st.error(f"定向生成失败：{msg}")
                else:
                    PROFILE.parent.mkdir(parents=True, exist_ok=True)
                    PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
                    with trace_step(
                        "chat", "docx", "生成基础版简历",
                        tool="docx_template",
                        why="没有选方向时，先生成一版基础简历，内容按你原来的信息保留。",
                        input_summary="未选方向",
                    ) as step:
                        ok, msg = _generate(profile, None)
                        step.finish(output_summary="已生成" if ok else msg, detail={"file": msg},
                                    status="done" if ok else "error")
                    if ok:
                        st.session_state.chat_generated = msg
                        st.session_state.chat_generated_hash = _profile_hash(profile, "")
                        st.session_state.chat_tailor_source = "base"
                        st.session_state.chat_tailor_warnings = []
                        st.session_state.chat_messages.append({"role": "assistant", "content": "已生成基础版简历。建议先选一个方向，再让我按方向整理。"})
                        st.rerun()
                    else:
                        st.error(f"生成失败：{msg}")
    with c2:
        if st.button("重新开始", use_container_width=True):
            st.session_state.chat_messages = [{"role": "assistant", "content": GREETING}]
            st.session_state.chat_profile = _blank()
            st.session_state.chat_generated = ""
            st.session_state.chat_generated_hash = ""
            st.session_state.selected_direction = ""
            st.session_state.chat_tailor_source = ""
            st.session_state.chat_tailor_warnings = []
            st.session_state.autofill_extra = {}
            try:
                PROFILE.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                pass
            st.rerun()

    if st.session_state.get("chat_tailor_warnings"):
        st.warning("整理结果有内容在原文中没找到，请核对：" + "；".join(st.session_state.chat_tailor_warnings[:5]))
    current_hash = _profile_hash(profile, st.session_state.get("selected_direction", ""))
    stale = bool(st.session_state.chat_generated) and st.session_state.get("chat_generated_hash") != current_hash
    if stale:
        st.info("信息已更新，旧简历已隐藏；请重新生成，新增经历才会进入简历。")
    if st.session_state.chat_generated and not stale:
        src = st.session_state.get("chat_tailor_source", "")
        if src == "llm":
            st.caption("生成方式：按方向整理（只基于已有事实；缺具体结果时用定性描述写完整）")
        elif src == "rule":
            st.caption("生成方式：基础整理")
        p = Path(st.session_state.chat_generated)
        if p.exists():
            st.download_button(
                "⬇ 下载我的简历",
                data=p.read_bytes(),
                file_name=p.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
