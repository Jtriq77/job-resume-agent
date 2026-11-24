"""用真实画像 JSON 填充主模板，输出简历 DOCX。

用法：
    python scripts/build_resume_from_profile.py --profile data/profile.json --out data/output/简历.docx
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docx import Document  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.text.paragraph import Paragraph  # noqa: E402

from src.agent.polish import polish_profile  # noqa: E402
from src.render.docx_filler import fill_template, flatten_profile  # noqa: E402


def _replace_photo(docx_path: Path, photo_path: Path) -> None:
    try:
        from PIL import Image, ImageOps
    except Exception:  # noqa: BLE001
        return
    img = Image.open(photo_path).convert("RGB")
    img = ImageOps.fit(img, (300, 400), method=Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    data = buf.getvalue()
    tmp = docx_path.with_suffix(".tmp.docx")
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)
            if item.filename == "word/media/image1.jpeg":
                raw = data
            zout.writestr(item, raw)
    tmp.replace(docx_path)


def _remove_paragraph(doc: Document, index: int) -> None:
    p = doc.paragraphs[index]
    p._element.getparent().remove(p._element)


def _set_text(p: Paragraph, text: str) -> None:
    if p.runs:
        p.runs[0].text = text
        for run in p.runs[1:]:
            run.text = ""
    else:
        p.add_run(text)


def _line(*parts: str) -> str:
    return "    ".join(str(x).strip() for x in parts if str(x).strip())


def _remove_element(e) -> None:
    parent = e.getparent()
    if parent is not None:
        parent.remove(e)


def _fill_block(doc: Document, elems: list, kind: str, item: dict, paragraph_mode: bool) -> None:
    """给克隆出来的段落块填内容；elems = [header, bullet1, bullet2, ...]。"""
    header = Paragraph(elems[0], doc._body)
    if kind == "education":
        _set_text(header, _line(item.get("date", ""), item.get("school", ""), item.get("major", ""), item.get("degree", "")))
        gpa_line = "- GPA：" + "；".join(x for x in [item.get("gpa", ""), item.get("extra", "")] if x)
        if gpa_line.strip() != "- GPA：":
            _set_text(Paragraph(elems[1], doc._body), gpa_line)
        else:
            _remove_element(elems[1])
        if item.get("courses"):
            _set_text(Paragraph(elems[2], doc._body), "- 相关课程：" + item["courses"])
        else:
            _remove_element(elems[2])
        for e in elems[3:]:
            _remove_element(e)
        return

    if kind == "internship":
        _set_text(header, _line(item.get("date", ""), item.get("company", ""), item.get("dept", ""), item.get("role", "")))
    else:
        _set_text(header, _line(item.get("date", ""), item.get("org", ""), item.get("role", "")))

    bullets = item.get("bullets") or []
    if paragraph_mode:
        para = "；".join(str(b).strip().rstrip("。；;，, ") for b in bullets if str(b).strip())
        if para:
            _set_text(Paragraph(elems[1], doc._body), para + "。")
        else:
            _remove_element(elems[1])
        for e in elems[2:]:
            _remove_element(e)
    else:
        for j, e in enumerate(elems[1:]):
            if j < len(bullets) and str(bullets[j]).strip():
                _set_text(Paragraph(e, doc._body), "- " + str(bullets[j]).strip())
            else:
                _remove_element(e)


def _capture_blocks(doc: Document, mapping: dict) -> dict[str, list]:
    """在删空段之前，把第二块（header + bullets）深拷贝出来，作为第 3+ 段的原型。"""
    out = {}
    for key in ("education", "internships", "campus"):
        block = mapping["slots"][key][1]
        idxs = [block["header"], *block["bullets"]]
        out[key] = [copy.deepcopy(doc.paragraphs[i]._p) for i in idxs]
    return out


def _clone_extra_items(doc: Document, profile: dict, mapping: dict, headings: dict, prototypes: dict) -> None:
    paragraph_mode = profile.get("_format") == "paragraph"
    spec = [
        ("educations", "education", "实习经历", "education"),
        ("internships", "internships", "校园与项目经历", "internship"),
        ("campus", "campus", "技能特长", "campus"),
    ]
    for list_key, slot_key, next_title, kind in spec:
        items = profile.get(list_key, [])
        if len(items) <= 2:
            continue
        next_heading = headings[next_title]
        for item in items[2:]:
            elems = [copy.deepcopy(e) for e in prototypes[slot_key]]
            for e in elems:
                next_heading.addprevious(e)
            _fill_block(doc, elems, kind, item, paragraph_mode)


def format_paragraph_blocks(doc: Document, profile: dict) -> None:
    """段落版：把所有以 "- " 开头的长段落改成正常段落。"""
    if profile.get("_format") != "paragraph":
        return
    for p in doc.paragraphs:
        text = p.text.strip()
        if text.startswith("- ") and len(text) > 60:
            text = text[2:].strip().replace("；。", "；").replace("。；", "。")
            text = re.sub(r"[。；;，,\s]+$", "", text) + "。"
            _set_text(p, text)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = 0
            p.paragraph_format.first_line_indent = 0
            p.paragraph_format.space_after = 4


def clean_education_labels(doc: Document) -> None:
    """GPA 为空但荣誉非空时，把 “- GPA：；荣誉” 改成 “- 荣誉：荣誉”。"""
    for p in doc.paragraphs:
        text = p.text.strip()
        if text.startswith("- GPA："):
            rest = text[len("- GPA："):].strip().lstrip("；;，, ").strip()
            if rest:
                _set_text(p, "- 荣誉：" + rest)
            else:
                _remove_element(p._p)


def prune_leftovers(doc: Document) -> None:
    """删掉没填上的占位符、空标签行（如 "- GPA：；"）。"""
    for idx in reversed(range(len(doc.paragraphs))):
        text = doc.paragraphs[idx].text.strip()
        empty_label = bool(re.match(r"^-\s*[^：:]{1,8}[：:]\s*[；;、，,\s]*$", text))
        if "{{" in text or text in ("-", "•", "·") or empty_label:
            p = doc.paragraphs[idx]
            p._element.getparent().remove(p._element)


def prune_optional_blocks(doc: Document, profile: dict) -> None:
    """按 template_map 的固定槽位，删掉没有内容的第二段/第三行，避免空白。"""
    mapping = json.loads((ROOT / "templates" / "template_map.json").read_text(encoding="utf-8"))
    slots = mapping["slots"]
    to_remove: list[int] = []
    if len(profile.get("educations", [])) < 2:
        # 7 是第二段教育前的空行，一并删掉，避免教育背景和实习之间出现大块空白
        to_remove += [7, slots["education"][1]["header"], *slots["education"][1]["bullets"]]
    if len(profile.get("internships", [])) < 2:
        to_remove += [slots["internships"][1]["header"], *slots["internships"][1]["bullets"]]
    if len(profile.get("campus", [])) < 2:
        to_remove += [slots["campus"][1]["header"], *slots["campus"][1]["bullets"]]
    # 技能行按填完后的实际文本判断，空行删掉
    for idx in slots["skills"]:
        if idx < len(doc.paragraphs) and not doc.paragraphs[idx].text.strip():
            to_remove.append(idx)
    for idx in sorted(set(to_remove), reverse=True):
        if 0 <= idx < len(doc.paragraphs):
            _remove_paragraph(doc, idx)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="data/profile.json")
    ap.add_argument("--template", default="templates/01_主模板_产品运营_单页_可填充.docx")
    ap.add_argument("--out", default="data/output/简历.docx")
    ap.add_argument("--photo", default="")
    args = ap.parse_args()

    profile_path = Path(args.profile)
    if not profile_path.exists():
        raise SystemExit(f"画像不存在：{profile_path}")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    # 生成前统一润色：只改写，不新增事实；段落版已经由 tailor 写好，不能再拆成 bullet
    if profile.get("_format") != "paragraph":
        profile, _changes = polish_profile(profile)
    template = Path(args.template)
    if not template.exists():
        raise SystemExit(f"模板不存在：{template}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fill_template(template, out, flatten_profile(profile))

    doc = Document(str(out))
    mapping = json.loads((ROOT / "templates" / "template_map.json").read_text(encoding="utf-8"))
    headings = {}
    for p in doc.paragraphs:
        t = p.text.strip()
        for name in ("教育背景", "实习经历", "校园与项目经历", "技能特长"):
            if t.startswith(name):
                headings[name] = p._p
    prototypes = _capture_blocks(doc, mapping)

    # 先按原始模板索引删掉没有内容的第二块，再克隆第 3+ 段
    prune_optional_blocks(doc, profile)
    _clone_extra_items(doc, profile, mapping, headings, prototypes)
    format_paragraph_blocks(doc, profile)
    clean_education_labels(doc)
    prune_leftovers(doc)
    # 模板里日期为空时会留下前导空格，统一去掉，避免经历标题缩进
    for p in doc.paragraphs:
        text = p.text
        if text.strip() and text != text.strip() and not text.strip().startswith("-"):
            _set_text(p, text.strip())
    doc.save(out)
    if args.photo and Path(args.photo).exists():
        _replace_photo(out, Path(args.photo))

    leftovers = [p.text for p in doc.paragraphs if "{{" in p.text]
    print(f"写入 {out}")
    print("残留占位符：", leftovers or "无")
    print("段落数：", len(doc.paragraphs))


if __name__ == "__main__":
    main()
