"""批量体检 DOCX 简历模板，输出可排序的质量表。

用法：
    python scripts/audit_templates.py --dir 简历模版 --out data/template_audit.csv

指标：
- 页数（docProps/app.xml）
- 表格数、文本框数、分栏数、图片数、段落数、字符数
- 区块覆盖（教育/实习/项目/技能/校园/证书/荣誉/自我评价）
- 占位符数量
- 综合分（ATS 友好 + 单页 + 内容完整）
"""

from __future__ import annotations

import argparse
import csv
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
EP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

SECTIONS = {
    "教育": ["教育", "学历", "院校"],
    "实习/工作": ["实习", "工作经历", "工作经验", "实践"],
    "项目": ["项目", "科研", "课题"],
    "技能": ["技能", "专业能力", "IT 技能", "IT技能"],
    "校园": ["校园", "社团", "学生工作", "组织"],
    "证书": ["证书", "资格", "语言"],
    "荣誉": ["荣誉", "获奖", "奖项", "奖学金"],
    "自我评价": ["自我评价", "个人评价", "自我介绍", "summary"],
}


def text_of(root: ET.Element) -> str:
    return "".join(t.text or "" for t in root.iter(f"{{{W}}}t")).strip()


def audit(path: Path) -> dict:
    row = {"file": str(path), "name": path.name, "ok": False, "error": ""}
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            doc = ET.fromstring(z.read("word/document.xml"))
            text = text_of(doc)
            tables = len(list(doc.iter(f"{{{W}}}tbl")))
            textboxes = len(list(doc.iter(f"{{{W}}}txbxContent")))
            drawings = len(list(doc.iter(f"{{{W}}}drawing"))) + len(list(doc.iter(f"{{{W}}}pict")))
            paras = len(list(doc.iter(f"{{{W}}}p")))
            cols = 1
            for c in doc.iter(f"{{{W}}}cols"):
                val = c.get(f"{{{W}}}num")
                if val and val.isdigit():
                    cols = max(cols, int(val))
            pages = None
            if "docProps/app.xml" in names:
                try:
                    app = ET.fromstring(z.read("docProps/app.xml"))
                    for tag in ("Pages", f"{{{EP}}}Pages"):
                        el = app.find(tag)
                        if el is not None and (el.text or "").strip().isdigit():
                            pages = int(el.text.strip())
                            break
                except Exception:  # noqa: BLE001
                    pass
            found = [k for k, words in SECTIONS.items() if any(w.lower() in text.lower() for w in words)]
            placeholders = len(re.findall(r"\{\{|\}\}", text))
            row.update({
                "ok": True,
                "pages": pages,
                "tables": tables,
                "textboxes": textboxes,
                "columns": cols,
                "images": drawings,
                "paragraphs": paras,
                "chars": len(text),
                "sections": "/".join(found),
                "section_count": len(found),
                "placeholders": placeholders,
                "has_name": "姓名" in text,
                "text_snippet": text[:120].replace("\n", " "),
            })
            # 分数
            score = 0
            score += 25 if pages == 1 else 12 if pages == 2 else 0
            score += 15 if textboxes == 0 else 0
            score += 10 if cols <= 1 else 0
            score += 15 if len(found) >= 4 else 8 if len(found) == 3 else 0
            score += 15 if 800 <= len(text) <= 3000 else 8 if 500 <= len(text) <= 4000 else 0
            score += 10 if tables <= 2 else 5 if tables <= 4 else 0
            score += 5 if drawings <= 2 else 0
            score += 5 if placeholders > 0 else 0
            name = path.name
            if any(k in name for k in ["数据", "产品", "运营", "互联网", "大厂", "通用", "单页"]):
                score += 5
            row["score"] = score
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    return row


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="简历模版")
    ap.add_argument("--out", default="data/template_audit.csv")
    args = ap.parse_args()
    root = Path(args.dir)
    files = sorted(root.rglob("*.docx"))
    rows = [audit(p) for p in files]
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = ["file", "name", "ok", "error", "score", "pages", "tables", "textboxes", "columns",
            "images", "paragraphs", "chars", "sections", "section_count", "placeholders", "has_name", "text_snippet"]
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})
    ok = [r for r in rows if r.get("ok")]
    ok.sort(key=lambda r: (-r["score"], r["pages"] or 99, r["chars"]))
    print(f"扫描 {len(files)} 个 DOCX，成功 {len(ok)}")
    print(f"{'score':>5} {'pages':>5} {'tbl':>4} {'tbx':>4} {'col':>4} {'chars':>6} {'sections':<20} name")
    for r in ok[:40]:
        print(f"{r['score']:>5} {str(r.get('pages')):>5} {r['tables']:>4} {r['textboxes']:>4} {r['columns']:>4} "
              f"{r['chars']:>6} {r['sections'][:19]:<20} {r['name']}")
    print(f"\n写入 {out}")


if __name__ == "__main__":
    main()
