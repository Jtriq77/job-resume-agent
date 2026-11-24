"""极简 DOCX 占位符填充：把 {{key}} 替换为 values[key]。

适用于固定槽位模板（本项目的 01_主模板）。不做循环/条件，后续可升级为 docxtpl。
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document

PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _replace_paragraph(paragraph, values: dict[str, str]) -> None:
    # 先逐 run 替换，尽量保留格式
    for run in paragraph.runs:
        if "{{" in run.text:
            run.text = PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), run.text)
    # 跨 run 的占位符：重建为第一个 run 格式
    if "{{" in paragraph.text:
        new_text = PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), paragraph.text)
        if paragraph.runs:
            paragraph.runs[0].text = new_text
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(new_text)


def fill_template(template: str | Path, output: str | Path, values: dict[str, str]) -> Path:
    doc = Document(str(template))
    for p in doc.paragraphs:
        _replace_paragraph(p, values)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    _replace_paragraph(p, values)
    for section in doc.sections:
        for p in section.header.paragraphs:
            _replace_paragraph(p, values)
        for p in section.footer.paragraphs:
            _replace_paragraph(p, values)
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)
    return out


def flatten_profile(profile: dict) -> dict[str, str]:
    """把示例 JSON 拍平成模板占位符需要的 key。"""
    v: dict[str, str] = {
        "name": profile["name"],
        "job_intent": profile["job_intent"],
        "contact": profile["contact"],
    }
    for i, edu in enumerate(profile.get("educations", []), start=1):
        v[f"edu{i}_date"] = edu.get("date", "")
        v[f"edu{i}_school"] = edu.get("school", "")
        v[f"edu{i}_major"] = edu.get("major", "")
        v[f"edu{i}_degree"] = edu.get("degree", "")
        v[f"edu{i}_gpa"] = edu.get("gpa", "")
        v[f"edu{i}_extra"] = edu.get("extra", "")
        v[f"edu{i}_courses"] = edu.get("courses", "")
    for i, it in enumerate(profile.get("internships", []), start=1):
        v[f"int{i}_date"] = it.get("date", "")
        v[f"int{i}_company"] = it.get("company", "")
        v[f"int{i}_dept"] = it.get("dept", "")
        v[f"int{i}_role"] = it.get("role", "")
        for j, b in enumerate(it.get("bullets", []), start=1):
            v[f"int{i}_b{j}"] = b
    for i, it in enumerate(profile.get("campus", []), start=1):
        v[f"cam{i}_date"] = it.get("date", "")
        v[f"cam{i}_org"] = it.get("org", "")
        v[f"cam{i}_role"] = it.get("role", "")
        for j, b in enumerate(it.get("bullets", []), start=1):
            v[f"cam{i}_b{j}"] = b
    lang, tools, certs = [], [], []
    for s in profile.get("skills", []):
        s = str(s).strip()
        if not s:
            continue
        if s.startswith("语言："):
            lang.append(s[3:].strip())
        elif s.startswith("工具："):
            tools.append(s[3:].strip())
        elif s.startswith("证书/其他：") or s.startswith("证书："):
            certs.append(s.split("：", 1)[1].strip())
        elif any(k in s for k in ["CET", "英语", "雅思", "托福", "日语", "四级", "六级"]):
            lang.append(s)
        elif any(k in s for k in ["证书", "资格", "二级", "三级", "初级", "CPA", "教资"]):
            certs.append(s)
        else:
            tools.append(s)
    lines = []
    if lang:
        lines.append("语言：" + "、".join(lang))
    if tools:
        lines.append("工具：" + "、".join(tools))
    if certs:
        lines.append("证书/其他：" + "、".join(certs))
    for i in range(3):
        v[f"skill{i+1}"] = lines[i] if i < len(lines) else ""
    return v
