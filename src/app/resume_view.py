"""简历模板页：主模板一键生成 + 原始模板画廊（筛选、预览、下载）。"""

from __future__ import annotations

import base64
import html
import json
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st

from src.app.trace_panel import trace_once, trace_record

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

GALLERY_PATH = ROOT / "templates" / "gallery.json"
PRIMARY_FILLABLE = ROOT / "templates" / "01_主模板_产品运营_单页_可填充.docx"
PRIMARY_SOURCE = ROOT / "templates" / "01_主模板_产品运营_单页.docx"


def _docx_python() -> str | None:
    """找一个能 import docx 的解释器；venv 里 lxml 可能因签名限制失败。"""
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


def _generate_sample() -> bool:
    py = _docx_python()
    if not py:
        return False
    r = subprocess.run(
        [py, str(ROOT / "scripts" / "build_sample_resume.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stderr)
        return False
    return True


def _load_gallery() -> list[dict]:
    if not GALLERY_PATH.exists():
        return []
    try:
        return json.loads(GALLERY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def _image_html(path: Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"<img src='data:image/png;base64,{data}' style='width:100%;border-radius:8px;margin-bottom:8px'/>"


def _placeholder(name: str) -> str:
    return (
        "<div style='height:190px;border:1px dashed #c7cdd6;border-radius:8px;"
        "display:flex;align-items:center;justify-content:center;flex-direction:column;"
        "background:#f7f8fa;color:#667085;font-size:13px;margin-bottom:8px'>"
        "<div style='font-size:28px;font-weight:700;letter-spacing:1px'>模板</div>"
        f"<div style='margin-top:6px'>{html.escape(name[:22])}</div>"
        "</div>"
    )


def _passes(item: dict, q: str, pages: str, layout: str, kind: str) -> bool:
    hay = (item.get("name", "") + " " + " ".join(item.get("tags", []))).lower()
    if q and q.lower() not in hay:
        return False
    tags = item.get("tags", [])
    if pages == "1 页" and "单页" not in tags:
        return False
    if pages == "2 页" and "两页" not in tags:
        return False
    if layout == "单栏" and "单栏" not in tags:
        return False
    if layout == "双栏" and "双栏" not in tags:
        return False
    if kind == "纯文本" and "纯文本" not in tags:
        return False
    if kind == "文本框版" and "文本框版" not in tags:
        return False
    if kind == "表格版" and "表格版" not in tags:
        return False
    return True


def render_resume_tab() -> None:
    st.subheader("简历模板")
    st.caption("从 497 份模板里挑出 21 个代表模板；主模板可以直接生成，其余可以预览、下载后自己编辑。")

    gallery = _load_gallery()
    trace_once(
        "resume", "gallery", "读取模板",
        tool="templates/gallery.json",
        why="从模板库里挑出不同页数、不同风格的代表模板。",
        output_summary=f"{len(gallery)} 个模板，{sum(1 for x in gallery if x.get('preview'))} 个有预览",
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("原始模板", "497")
    c2.metric("单页模板", "421")
    c3.metric("干净单栏", "13")
    c4.metric("画廊/可预览", f"{len(gallery)} / {sum(1 for x in gallery if x.get('preview'))}")

    # 主模板：唯一接入一键生成的模板
    with st.container(border=True):
        a, b = st.columns([0.55, 0.45])
        with a:
            st.markdown("### ✅ 主模板 · 可一键生成")
            st.caption("单页、单栏、排版干净；适合数据、产品、运营和技术方向。")
            st.write("**特点**：8 个区块 · 2239 字 · 支持段落版 · 第 3 段及以后自动扩展")
        with b:
            if PRIMARY_FILLABLE.exists():
                st.download_button(
                    "⬇ 下载主模板",
                    data=PRIMARY_FILLABLE.read_bytes(),
                    file_name=PRIMARY_FILLABLE.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            if st.button("用示例信息生成一份简历", use_container_width=True):
                if _generate_sample():
                    st.session_state["sample_resume_ready"] = True
                    trace_record(
                        "resume", "sample", "生成示例简历",
                        tool="build_sample_resume.py",
                        why="用一份示例信息生成简历，检查模板效果。",
                        output_summary="已生成 1 页示例简历",
                    )
                    st.success("已生成 1 页示例简历（示例数据）")
                else:
                    st.error("生成失败：当前环境缺少文档处理组件。")
        st.info("要生成你自己的简历：去「📝 信息采集」填写 → 保存 → 选方向 → 生成。")

    st.markdown("---")
    st.markdown("### 🗂 模板库")
    st.caption("按页数、版式、类型筛选；点「下载原模板」可以直接打开编辑。")

    f1, f2, f3, f4 = st.columns([0.4, 0.2, 0.2, 0.2])
    q = f1.text_input("搜索模板", placeholder="大厂、银行、彩色、两页…", key="tpl_q")
    pages = f2.selectbox("页数", ["全部", "1 页", "2 页"], key="tpl_pages")
    layout = f3.selectbox("版式", ["全部", "单栏", "双栏"], key="tpl_layout")
    kind = f4.selectbox("类型", ["全部", "纯文本", "文本框版", "表格版"], key="tpl_kind")

    shown = [x for x in gallery if _passes(x, q, pages, layout, kind)]
    st.caption(f"当前显示 {len(shown)} / {len(gallery)} 个模板")

    if not shown:
        st.warning("没有匹配的模板，换个关键词或筛选条件。")
        return

    cols = st.columns(3)
    for idx, item in enumerate(shown):
        with cols[idx % 3]:
            with st.container(border=True):
                preview = item.get("preview")
                preview_path = ROOT / preview if preview else None
                if preview_path and preview_path.exists():
                    st.markdown(_image_html(preview_path), unsafe_allow_html=True)
                else:
                    st.markdown(_placeholder(item.get("name", "模板")), unsafe_allow_html=True)

                st.markdown(f"**{item.get('name', '模板')}**")
                st.caption(" · ".join(item.get("tags", [])))
                st.caption(
                    f"{item.get('pages', '?')} 页 · {item.get('columns', '?')} 栏 · "
                    f"{item.get('chars', '?')} 字"
                )
                st.caption(item.get("note", ""))
                src = ROOT / item["file"]
                if src.exists():
                    st.download_button(
                        "⬇ 下载原模板",
                        data=src.read_bytes(),
                        file_name=src.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"tpl_dl_{idx}",
                        use_container_width=True,
                    )


    sample = ROOT / "examples" / "sample_resume_产品运营.docx"
    if sample.exists():
        st.download_button(
            "⬇ 下载示例简历（虚构数据）",
            data=sample.read_bytes(),
            file_name="sample_resume_产品运营.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
