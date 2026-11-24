"""信息采集：把散装信息填成 profile.json，并直接生成简历。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import re

import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.profile_extract import apply_supplement, extract  # noqa: E402
from src.agent.direction import recommend_directions  # noqa: E402
from src.agent.tailor import tailor_profile  # noqa: E402
from src.app.trace_panel import trace_once, trace_record, trace_step  # noqa: E402

PROFILE = ROOT / "data" / "profile.json"
PHOTO = ROOT / "data" / "photo_upload"
OUT_DIR = ROOT / "data" / "output"

POLITICAL = ["不展示", "中共党员", "中共预备党员", "共青团员", "群众"]
DEGREES = ["本科", "硕士", "博士", "大专", "其他"]


def _lines(text: str, max_n: int = 3) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-•·").strip()
        if line:
            out.append(line)
    return out[:max_n]


def _docx_python() -> str | None:
    candidates = [
        os.environ.get("PYTHON_WITH_DOCX"),
        sys.executable,
        "python3",
    ]
    for p in candidates:
        if p and Path(p).exists():
            try:
                r = subprocess.run([p, "-c", "import docx"], capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    return p
            except Exception:  # noqa: BLE001
                continue
    return None


def _contact(phone: str, email: str, city: str, age: str, political: str, availability: str) -> str:
    parts = [phone.strip(), email.strip(), city.strip()]
    if age.strip():
        parts.append(f"{age.strip()}岁")
    if political != "不展示":
        parts.append(f"政治面貌：{political}")
    if availability.strip():
        parts.append(availability.strip())
    return " | ".join(p for p in parts if p)


def _edu_block(prefix: str, school: str, major: str, degree: str, start: str, end: str,
               gpa: str, rank: str, courses: str, awards: str) -> dict:
    date = f"{start.strip()}-{end.strip()}".strip("-")
    extra = "；".join(x for x in [rank.strip(), awards.strip()] if x)
    return {
        "date": date,
        "school": school.strip(),
        "major": major.strip(),
        "degree": degree,
        "gpa": gpa.strip(),
        "extra": extra,
        "courses": courses.strip(),
    }


def _intern_block(company: str, dept: str, role: str, start: str, end: str, bullets: str) -> dict:
    return {
        "date": f"{start.strip()}-{end.strip()}".strip("-"),
        "company": company.strip(),
        "dept": dept.strip(),
        "role": role.strip(),
        "bullets": _lines(bullets, 3),
    }


def _campus_block(kind: str, org: str, role: str, start: str, end: str, bullets: str) -> dict:
    return {
        "date": f"{start.strip()}-{end.strip()}".strip("-"),
        "org": f"{org.strip()}（{kind}）" if kind else org.strip(),
        "role": role.strip(),
        "bullets": _lines(bullets, 3),
    }


def _generate(profile: dict, photo_path: Path | None) -> tuple[bool, str]:
    py = _docx_python()
    if not py:
        return False, "找不到可 import docx 的 Python 解释器"
    name = profile.get("name") or "我的简历"
    out = OUT_DIR / f"简历_{name}.docx"
    cmd = [py, str(ROOT / "scripts" / "build_resume_from_profile.py"),
           "--profile", str(PROFILE), "--out", str(out)]
    if photo_path and photo_path.exists():
        cmd += ["--photo", str(photo_path)]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-800:]
    return True, str(out)


def _split_date(value: str) -> tuple[str, str]:
    v = str(value or "").strip()
    if not v:
        return "", ""
    if "届" in v:
        return "", v
    parts = re.split(r"\s*[-~至]\s*", v, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", v


def _campus_org(org: str) -> tuple[str, str]:
    text = str(org or "").strip()
    if text.endswith("（项目）") or "项目" in text:
        return "项目", text.replace("（项目）", "").strip()
    return "校园", text


def _skill_lines(skills: list) -> tuple[str, str, str]:
    lang: list[str] = []
    tools: list[str] = []
    certs: list[str] = []
    for s in skills:
        s = str(s).strip()
        if not s:
            continue
        if s.startswith("语言："):
            lang.append(s[3:].strip())
        elif s.startswith("工具："):
            tools.append(s[3:].strip())
        elif s.startswith("证书/其他：") or s.startswith("证书："):
            certs.append(s.split("：", 1)[1].strip())
        elif any(k in s for k in ["CET", "英语", "雅思", "托福", "四级", "六级"]):
            lang.append(s)
        elif any(k in s for k in ["证书", "资格", "二级", "三级", "初级"]):
            certs.append(s)
        else:
            tools.append(s)
    return "、".join(lang), "、".join(tools), "、".join(certs)


def profile_to_form(profile: dict) -> tuple[dict[str, str], dict[str, list]]:
    values: dict[str, str] = {
        "b_name": profile.get("name", ""),
        "b_age": profile.get("age", ""),
        "b_pol": profile.get("political_status", "不展示") if profile.get("political_status") in POLITICAL else "不展示",
        "b_phone": profile.get("phone", ""),
        "b_email": profile.get("email", ""),
        "b_city": profile.get("city", ""),
        "b_targets": "，".join(profile.get("target_cities", []) or []),
        "b_job": profile.get("job_intent", ""),
        "b_avail": profile.get("availability", ""),
    }
    edus = profile.get("educations", [])
    for i in (1, 2):
        if i <= len(edus):
            e = edus[i - 1]
            start, end = _split_date(str(e.get("date", "")))
            values[f"e{i}s"] = e.get("school", "")
            values[f"e{i}m"] = e.get("major", "")
            degree = e.get("degree", "本科")
            values[f"e{i}d"] = "硕士" if degree == "研究生" else (degree if degree in DEGREES else "本科")
            values[f"e{i}g"] = e.get("gpa", "")
            values[f"e{i}st"] = start
            values[f"e{i}en"] = end
            values[f"e{i}c"] = e.get("courses", "")
            values[f"e{i}a"] = e.get("extra", "")
    ints = profile.get("internships", [])
    for i in (1, 2):
        if i <= len(ints):
            it = ints[i - 1]
            start, end = _split_date(str(it.get("date", "")))
            values[f"i{i}c"] = it.get("company", "")
            values[f"i{i}d"] = it.get("dept", "")
            values[f"i{i}r"] = it.get("role", "")
            values[f"i{i}st"] = start
            values[f"i{i}en"] = end
            values[f"i{i}b"] = "\n".join(str(x) for x in it.get("bullets", []))
    camps = profile.get("campus", [])
    for i in (1, 2):
        if i <= len(camps):
            c = camps[i - 1]
            kind, org = _campus_org(c.get("org", ""))
            start, end = _split_date(str(c.get("date", "")))
            values[f"c{i}k"] = kind
            values[f"c{i}o"] = org
            values[f"c{i}r"] = c.get("role", "")
            values[f"c{i}st"] = start
            values[f"c{i}en"] = end
            values[f"c{i}b"] = "\n".join(str(x) for x in c.get("bullets", []))
    lang, tools, certs = _skill_lines(profile.get("skills", []))
    values["sk1"] = lang
    values["sk2"] = tools
    values["sk3"] = certs
    extras = {
        "educations": edus[2:],
        "internships": ints[2:],
        "campus": camps[2:],
    }
    return {k: str(v) for k, v in values.items() if str(v).strip()}, extras


def _apply_form_values(values: dict[str, str], overwrite: bool) -> int:
    filled = 0
    for key, value in values.items():
        if overwrite or not st.session_state.get(key):
            st.session_state[key] = value
            filled += 1
    return filled


def _generate_tailored(profile: dict, direction: str, photo_path: Path | None = None) -> tuple[bool, str]:
    py = _docx_python()
    if not py:
        return False, "找不到可 import docx 的 Python 解释器"
    path = ROOT / "data" / "profile_tailored.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    name = profile.get("name") or "我的简历"
    out = ROOT / "data" / "output" / f"简历_{name}_{direction}.docx"
    cmd = [py, str(ROOT / "scripts" / "build_resume_from_profile.py"),
           "--profile", str(path), "--out", str(out)]
    if photo_path and photo_path.exists():
        cmd += ["--photo", str(photo_path)]
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout)[-800:]
    return True, str(out)


def _render_form_direction() -> None:
    profile = st.session_state.get("form_profile")
    if not profile:
        return
    st.markdown("### 方向推荐")
    st.caption("先选一个方向，再把每段实习/项目/校园经历写成一整段连续文字；不选也可以先不生成。")
    dirs = recommend_directions(profile)
    trace_once(
        "intake", "direction", "方向推荐",
        tool="direction.recommend_directions",
        why="根据你填的信息，挑出 3 个比较适合的方向。",
        output_summary="、".join(d["name"] for d in dirs),
    )
    cols = st.columns(3)
    for i, d in enumerate(dirs):
        with cols[i]:
            st.markdown(f"**{d['name']}**")
            st.progress(min(1.0, float(d.get("score", 0))))
            st.caption(d.get("reason", ""))
            if d.get("missing"):
                st.caption("建议补充：" + "、".join(d["missing"][:3]))
            if st.button("选这个方向", key=f"form_dir_{d['name']}", use_container_width=True):
                st.session_state["form_direction"] = d["name"]
                st.session_state["form_generated"] = ""
                trace_record("intake", "pick_direction", "选择方向", tool="human_gate",
                             why="你选定方向后，才开始生成简历。", output_summary=d["name"])
                st.rerun()

    selected = st.session_state.get("form_direction", "")
    if selected:
        st.success(f"已选方向：**{selected}**")
        if st.button(f"按「{selected}」方向生成简历", type="primary", use_container_width=True):
            with st.spinner(f"正在按「{selected}」方向整理实习 / 项目 / 校园经历…"):
                with trace_step(
                    "intake", "tailor", f"按「{selected}」方向整理",
                    tool="resume-direction-tailor",
                    why="把每段实习、项目和校园经历写成一段完整的话；不编造没有的经历；经历多时自动增加段落。",
                    input_summary=f"方向：{selected}",
                ) as step:
                    tailored, source, warns = tailor_profile(profile, selected)
                    step.finish(
                        output_summary=f"实习 {len(tailored.get('internships', []))} 段 / 校园 {len(tailored.get('campus', []))} 段",
                        detail={"source": source, "warnings": warns},
                    )
                with trace_step(
                    "intake", "docx", "生成简历",
                    tool="docx_template",
                    why="把整理好的内容放进简历模板，生成一份完整的简历。",
                    input_summary=selected,
                ) as step:
                    photo = st.session_state.get("form_photo_path")
                    ok, msg = _generate_tailored(tailored, selected, Path(photo) if photo else None)
                    step.finish(output_summary="已生成" if ok else msg, detail={"file": msg},
                                status="done" if ok else "error")
            if ok:
                st.session_state["form_generated"] = msg
                st.session_state["form_source"] = source
                st.session_state["form_warnings"] = warns
                st.rerun()
            else:
                st.error(f"生成失败：{msg}")

    if st.session_state.get("form_warnings"):
        st.warning("整理结果有内容在原文中没找到，请核对：" + "；".join(st.session_state["form_warnings"][:5]))
    generated = st.session_state.get("form_generated")
    if generated:
        p = Path(generated)
        if p.exists():
            st.download_button(
                "⬇ 下载我的简历",
                data=p.read_bytes(),
                file_name=p.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )


def render_intake_tab() -> None:
    st.subheader("信息采集")
    st.caption("这里填你自己的信息；保存后可以直接生成一份简历。带 * 的必填。")

    st.markdown("### ⚡ 一段话自动填写")
    with st.expander("粘贴一段自我介绍，自动识别并填入下面表单", expanded=False):
        auto_text = st.text_area(
            "例如：我叫林晓，23岁，中共党员，上海，手机 13800000000，邮箱 lin@example.com。示例大学计算机技术硕士，本科示例理工大学软件工程。2025.03-2025.08 在某科技公司做数据分析实习，获得校级一等奖学金，技能 Python、SQL。",
            height=120,
            key="autofill_text",
        )
        c1, c2 = st.columns([0.6, 0.4])
        overwrite = c1.checkbox("覆盖表单里已有内容", value=True)
        if c2.button("识别并填入", type="primary", use_container_width=True):
            if not auto_text.strip():
                st.warning("先粘贴一段自我介绍。")
            else:
                with st.spinner("正在识别姓名、联系方式、教育、实习、项目与技能…"):
                    with trace_step(
                        "intake", "autofill", "一段话自动识别",
                        tool="resume-section-extractor",
                        why="把你粘贴的话分成教育、实习、校园与项目、技能四块，再填进下面的表单；超过两段的经历会先记住，提交时一起写进简历。",
                        input_summary=auto_text[:160],
                    ) as step:
                        profile, _source = extract(auto_text)
                        profile, added = apply_supplement(profile, auto_text)
                        values, extras = profile_to_form(profile)
                        filled = _apply_form_values(values, overwrite)
                        step.finish(
                            output_summary=f"填入 {filled} 项；教育 {len(profile.get('educations', []))} / 实习 {len(profile.get('internships', []))} / 校园 {len(profile.get('campus', []))}",
                            detail={"added": added, "extra_counts": {k: len(v) for k, v in extras.items()}},
                        )
                    st.session_state["autofill_extra"] = extras
                    msg = f"已填入 {filled} 项。"
                    if added:
                        msg += " 补充识别：" + "、".join(dict.fromkeys(added)) + "。"
                    if any(extras.values()):
                        msg += " 有超过 2 段的经历，表单只展示前 2 段，其余会保留并写入简历。"
                    st.session_state["autofill_msg"] = msg
                    st.session_state["form_generated"] = ""
                    st.session_state["form_direction"] = ""
                    st.rerun()

    if st.session_state.get("autofill_msg"):
        st.success(st.session_state["autofill_msg"])

    if PROFILE.exists():
        st.info("已有信息，可继续修改后重新生成。")

    with st.form("intake_form", clear_on_submit=False):
        st.markdown("### 1. 基本信息")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("姓名 *", key="b_name")
        age = c2.text_input("年龄", placeholder="22", key="b_age")
        political = c3.selectbox("政治面貌", POLITICAL, index=0, key="b_pol")
        c1, c2 = st.columns(2)
        phone = c1.text_input("手机 *", placeholder="138****1234", key="b_phone")
        email = c2.text_input("邮箱 *", placeholder="you@example.com", key="b_email")
        c1, c2, c3 = st.columns(3)
        city = c1.text_input("所在城市", placeholder="上海", key="b_city")
        target_cities = c2.text_input("目标城市（逗号分隔）", placeholder="上海,杭州", key="b_targets")
        job_intent = c3.text_input("求职意向", placeholder="数据分析 / 产品运营", key="b_job")
        availability = st.text_input("到岗时间 / 实习天数", placeholder="可实习 4 天/周，7 月到岗", key="b_avail")
        photo = st.file_uploader("照片（选填，JPG/PNG；不传则用 PHOTO 占位）", type=["jpg", "jpeg", "png"])

        st.markdown("### 2. 教育经历")
        c1, c2, c3, c4 = st.columns(4)
        edu1_school = c1.text_input("学校 *", key="e1s")
        edu1_major = c2.text_input("专业 *", key="e1m")
        edu1_degree = c3.selectbox("学历", DEGREES, key="e1d")
        edu1_gpa = c4.text_input("GPA / 排名", placeholder="3.7/4.0（前10%）", key="e1g")
        c1, c2, c3 = st.columns(3)
        edu1_start = c1.text_input("开始时间", placeholder="2022.09", key="e1st")
        edu1_end = c2.text_input("结束时间", placeholder="2026.06", key="e1en")
        edu1_courses = c3.text_input("核心课程（5–8 门）", placeholder="数据库、统计学、机器学习", key="e1c")
        edu1_awards = st.text_area("竞赛 / 荣誉（每行一条）", height=80, placeholder="国家奖学金\n数学建模省二", key="e1a")

        with st.expander("第二段教育（选填：辅修 / 交换 / 双学位）"):
            c1, c2, c3, c4 = st.columns(4)
            edu2_school = c1.text_input("学校", key="e2s")
            edu2_major = c2.text_input("专业", key="e2m")
            edu2_degree = c3.selectbox("学历", DEGREES, key="e2d")
            edu2_gpa = c4.text_input("GPA / 排名", key="e2g")
            c1, c2, c3 = st.columns(3)
            edu2_start = c1.text_input("开始时间", key="e2st")
            edu2_end = c2.text_input("结束时间", key="e2en")
            edu2_courses = c3.text_input("核心课程", key="e2c")
            edu2_awards = st.text_area("竞赛 / 荣誉", height=60, key="e2a")

        st.markdown("### 3. 实习经历")
        c1, c2, c3 = st.columns(3)
        int1_company = c1.text_input("公司", key="i1c")
        int1_dept = c2.text_input("部门", key="i1d")
        int1_role = c3.text_input("岗位", key="i1r")
        c1, c2 = st.columns(2)
        int1_start = c1.text_input("开始时间", key="i1st")
        int1_end = c2.text_input("结束时间", key="i1en")
        int1_bullets = st.text_area("工作内容 / 成果（每行一条，最多 3 条）", height=110, key="i1b")

        with st.expander("第二段实习（选填）"):
            c1, c2, c3 = st.columns(3)
            int2_company = c1.text_input("公司", key="i2c")
            int2_dept = c2.text_input("部门", key="i2d")
            int2_role = c3.text_input("岗位", key="i2r")
            c1, c2 = st.columns(2)
            int2_start = c1.text_input("开始时间", key="i2st")
            int2_end = c2.text_input("结束时间", key="i2en")
            int2_bullets = st.text_area("工作内容 / 成果", height=110, key="i2b")

        st.markdown("### 4. 项目 / 校园经历")
        st.caption("模板只有 2 个槽位；建议 1 段项目 + 1 段校园，或 2 段项目。")
        c1, c2, c3 = st.columns(3)
        cam1_kind = c1.selectbox("类型", ["项目", "校园"], key="c1k")
        cam1_org = c2.text_input("项目 / 组织名称", key="c1o")
        cam1_role = c3.text_input("角色", key="c1r")
        c1, c2 = st.columns(2)
        cam1_start = c1.text_input("开始时间", key="c1st")
        cam1_end = c2.text_input("结束时间", key="c1en")
        cam1_bullets = st.text_area("内容 / 成果（每行一条，最多 3 条）", height=110, key="c1b")

        with st.expander("第二段项目 / 校园（选填）"):
            c1, c2, c3 = st.columns(3)
            cam2_kind = c1.selectbox("类型", ["项目", "校园"], key="c2k")
            cam2_org = c2.text_input("项目 / 组织名称", key="c2o")
            cam2_role = c3.text_input("角色", key="c2r")
            c1, c2 = st.columns(2)
            cam2_start = c1.text_input("开始时间", key="c2st")
            cam2_end = c2.text_input("结束时间", key="c2en")
            cam2_bullets = st.text_area("内容 / 成果", height=110, key="c2b")

        st.markdown("### 5. 技能 / 证书")
        c1, c2 = st.columns(2)
        lang = c1.text_input("语言", placeholder="CET-6（560）", key="sk1")
        tools = c2.text_input("工具 / 技术", placeholder="SQL、Python、Tableau", key="sk2")
        certs = st.text_input("证书 / 其他", placeholder="计算机二级、数据分析师初级", key="sk3")

        submitted = st.form_submit_button("保存信息，下一步选方向", type="primary", use_container_width=True)

    if not submitted:
        _render_form_direction()
        return

    missing = []
    if not name.strip():
        missing.append("姓名")
    if not phone.strip():
        missing.append("手机")
    if not email.strip():
        missing.append("邮箱")
    if not edu1_school.strip() or not edu1_major.strip():
        missing.append("学校/专业")
    if missing:
        st.error("还差必填项：" + "、".join(missing))
        return

    educations = [_edu_block("edu1", edu1_school, edu1_major, edu1_degree, edu1_start, edu1_end,
                             edu1_gpa, "", edu1_courses, edu1_awards)]
    if edu2_school.strip() or edu2_major.strip():
        educations.append(_edu_block("edu2", edu2_school, edu2_major, edu2_degree, edu2_start, edu2_end,
                                     edu2_gpa, "", edu2_courses, edu2_awards))

    internships = []
    if int1_company.strip() or int1_role.strip():
        internships.append(_intern_block(int1_company, int1_dept, int1_role, int1_start, int1_end, int1_bullets))
    if int2_company.strip() or int2_role.strip():
        internships.append(_intern_block(int2_company, int2_dept, int2_role, int2_start, int2_end, int2_bullets))

    campus = []
    if cam1_org.strip():
        campus.append(_campus_block(cam1_kind, cam1_org, cam1_role, cam1_start, cam1_end, cam1_bullets))
    if cam2_org.strip():
        campus.append(_campus_block(cam2_kind, cam2_org, cam2_role, cam2_start, cam2_end, cam2_bullets))

    skills = []
    if lang.strip():
        skills.append(f"语言：{lang.strip()}")
    if tools.strip():
        skills.append(f"工具：{tools.strip()}")
    if certs.strip():
        skills.append(f"证书/其他：{certs.strip()}")

    profile = {
        "name": name.strip(),
        "age": age.strip(),
        "political_status": political,
        "phone": phone.strip(),
        "email": email.strip(),
        "city": city.strip(),
        "target_cities": [x.strip() for x in target_cities.replace("，", ",").split(",") if x.strip()],
        "job_intent": job_intent.strip() or "数据分析 / 产品运营",
        "availability": availability.strip(),
        "contact": _contact(phone, email, city, age, political, availability),
        "educations": educations,
        "internships": internships,
        "campus": campus,
        "skills": skills,
    }

    # 自动识别时，超过表单 2 段的经历保存在 autofill_extra，提交时合并回去
    extra = st.session_state.get("autofill_extra") or {}
    for key in ("educations", "internships", "campus"):
        existing = profile.get(key, [])
        for item in extra.get(key, []):
            if item not in existing:
                existing.append(item)
        profile[key] = existing

    PROFILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    photo_path = None
    if photo is not None:
        photo_path = PHOTO.with_suffix(Path(photo.name).suffix.lower())
        photo_path.write_bytes(photo.getbuffer())
    st.session_state["profile"] = profile
    st.session_state["form_profile"] = profile
    st.session_state["form_photo_path"] = str(photo_path) if photo_path else st.session_state.get("form_photo_path", "")
    st.session_state["form_direction"] = ""
    st.session_state["form_generated"] = ""
    st.session_state["form_source"] = ""
    st.session_state["form_warnings"] = []
    trace_record(
        "intake", "save", "保存信息",
        tool="form_to_profile",
        why="把表单里的内容整理成教育、实习、校园与项目、技能四块，保留自动识别出的额外经历。",
        output_summary=f"教育 {len(profile.get('educations', []))} / 实习 {len(profile.get('internships', []))} / 校园 {len(profile.get('campus', []))} / 技能 {len(profile.get('skills', []))}",
    )
    st.success("信息已保存。请在下面选择方向，再生成简历。")
    _render_form_direction()
