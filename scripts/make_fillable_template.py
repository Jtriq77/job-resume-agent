"""把选中的主模板变成可填充模板：替换样例文字为占位符，并换掉样例照片。

用法：
    python scripts/make_fillable_template.py

输出：
    templates/01_主模板_产品运营_单页_可填充.docx
    templates/photo_placeholder.jpg
    templates/template_map.json
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from docx import Document

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "templates" / "01_主模板_产品运营_单页.docx"
OUT = ROOT / "templates" / "01_主模板_产品运营_单页_可填充.docx"
PHOTO = ROOT / "templates" / "photo_placeholder.jpg"

REPLACEMENTS = {
    0: "{{name}}",
    1: "求职意向：{{job_intent}}",
    2: "{{contact}}",
    4: "{{edu1_date}}    {{edu1_school}}    {{edu1_major}}    {{edu1_degree}}",
    5: "- GPA：{{edu1_gpa}}；{{edu1_extra}}",
    6: "- 相关课程：{{edu1_courses}}",
    8: "{{edu2_date}}    {{edu2_school}}    {{edu2_major}}    {{edu2_degree}}",
    9: "- GPA：{{edu2_gpa}}；{{edu2_extra}}",
    10: "- 相关课程：{{edu2_courses}}",
    12: "{{int1_date}}    {{int1_company}}    {{int1_dept}}    {{int1_role}}",
    13: "- {{int1_b1}}",
    14: "- {{int1_b2}}",
    15: "- {{int1_b3}}",
    16: "{{int2_date}}    {{int2_company}}    {{int2_dept}}    {{int2_role}}",
    17: "- {{int2_b1}}",
    18: "- {{int2_b2}}",
    19: "- {{int2_b3}}",
    20: "校园与项目经历",
    21: "{{cam1_date}}    {{cam1_org}}    {{cam1_role}}",
    22: "- {{cam1_b1}}",
    23: "- {{cam1_b2}}",
    24: "- {{cam1_b3}}",
    25: "{{cam2_date}}    {{cam2_org}}    {{cam2_role}}",
    26: "- {{cam2_b1}}",
    27: "- {{cam2_b2}}",
    28: "- {{cam2_b3}}",
    30: "{{skill1}}",
    31: "{{skill2}}",
    32: "{{skill3}}",
}


def make_photo() -> None:
    img = Image.new("RGB", (300, 400), (238, 241, 245))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 28)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    text = "PHOTO"
    bbox = d.textbbox((0, 0), text, font=font)
    d.text(((300 - (bbox[2] - bbox[0])) / 2, (400 - (bbox[3] - bbox[1])) / 2), text, fill=(160, 168, 178), font=font)
    img.save(PHOTO, "JPEG", quality=90)


def replace_photo(src: Path, dst: Path) -> None:
    make_photo()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/media/image1.jpeg":
                data = PHOTO.read_bytes()
            zout.writestr(item, data)


def _has_drawing(run) -> bool:
    xml = run._element.xml
    return "<w:drawing" in xml or "<w:pict" in xml


def set_text_keep_first_run(paragraph, text: str) -> None:
    """替换文字，但保留图片/悬浮对象所在的 run，避免把照片删掉。"""
    if not paragraph.runs:
        paragraph.add_run(text)
        return
    text_runs = [r for r in paragraph.runs if not _has_drawing(r)]
    if not text_runs:
        paragraph.add_run(text)
        return
    first = text_runs[0]
    first.text = text
    for run in text_runs[1:]:
        run.text = ""


def main() -> None:
    replace_photo(SRC, OUT)
    doc = Document(OUT)
    for idx, text in REPLACEMENTS.items():
        set_text_keep_first_run(doc.paragraphs[idx], text)
    doc.save(OUT)

    mapping = {
        "file": OUT.name,
        "source": SRC.name,
        "pages": 1,
        "columns": 1,
        "tables": 0,
        "textboxes": 0,
        "photo": "{{photo}}（当前为 PHOTO 占位图）",
        "slots": {
            "header": {"name": 0, "job_intent": 1, "contact": 2},
            "education": [
                {"header": 4, "bullets": [5, 6]},
                {"header": 8, "bullets": [9, 10]},
            ],
            "internships": [
                {"header": 12, "bullets": [13, 14, 15]},
                {"header": 16, "bullets": [17, 18, 19]},
            ],
            "campus": [
                {"header": 21, "bullets": [22, 23, 24]},
                {"header": 25, "bullets": [26, 27, 28]},
            ],
            "skills": [30, 31, 32],
        },
        "limits": {
            "education": 2,
            "internships": 2,
            "campus": 2,
            "skills": 3,
            "note": "固定槽位；超出需要复制段落块，后续版本支持动态循环。",
        },
        "placeholders": sorted(set(REPLACEMENTS.values())),
    }
    (ROOT / "templates" / "template_map.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {OUT}")
    print(f"写入 {PHOTO}")
    print(f"写入 templates/template_map.json")
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip():
            print(f"{i:03d} | {p.text[:100]}")


if __name__ == "__main__":
    main()
