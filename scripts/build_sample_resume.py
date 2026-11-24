"""用示例画像填充主模板，生成 examples/sample_resume_产品运营.docx。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.render.docx_filler import fill_template, flatten_profile  # noqa: E402


def main() -> None:
    profile = json.loads((ROOT / "examples" / "sample_profile.json").read_text(encoding="utf-8"))
    values = flatten_profile(profile)
    out = fill_template(
        ROOT / "templates" / "01_主模板_产品运营_单页_可填充.docx",
        ROOT / "examples" / "sample_resume_产品运营.docx",
        values,
    )
    print(f"写入 {out}")
    from docx import Document
    doc = Document(str(out))
    leftovers = [p.text for p in doc.paragraphs if "{{" in p.text]
    print("残留占位符：", leftovers or "无")
    for p in doc.paragraphs:
        if p.text.strip():
            print(p.text[:110])


if __name__ == "__main__":
    main()
