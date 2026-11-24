"""按选定方向整理简历经历。

文本模型 API 可用时走模型；失败/无 key 时回退到已有的整理结果。
只整理已有事实，数字/公司/学校回查原文；缺具体结果时用定性描述写完整，不写占位符。
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = ROOT / "skills" / "resume-direction-tailor" / "prompt.md"

try:
    from .profile_extract import _load_env
    _load_env()
except Exception:  # noqa: BLE001
    pass


def _compact(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": profile.get("name", ""),
        "job_intent": profile.get("job_intent", ""),
        "educations": profile.get("educations", []),
        "internships": profile.get("internships", []),
        "campus": profile.get("campus", []),
        "skills": profile.get("skills", []),
    }


def _source_text(profile: dict[str, Any]) -> str:
    parts = [str(profile.get("job_intent", ""))] + [str(x) for x in profile.get("skills", [])]
    for key in ("educations", "internships", "campus"):
        for item in profile.get(key, []):
            parts.append(json.dumps(item, ensure_ascii=False))
    return "\n".join(parts)


def _clean_para(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\[待补充\]|（待补充）|\(待补充\)|\[待填\]|（待填）|XX+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip("；;，,。 ")


def _as_paragraph(item: dict[str, Any]) -> str:
    if item.get("paragraph"):
        return _clean_para(item["paragraph"])
    bullets = item.get("bullets") or []
    if isinstance(bullets, str):
        return _clean_para(bullets)
    return _clean_para("；".join(str(b) for b in bullets if str(b).strip()))


def _normalize(original: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(original)
    if "education" in raw and "educations" not in raw:
        raw["educations"] = raw.pop("education")
    if "projects" in raw and "campus" not in raw:
        raw["campus"] = raw.pop("projects")
    for key in ("educations", "internships", "campus"):
        new_items = raw.get(key)
        if not isinstance(new_items, list) or not new_items:
            continue
        old_items = out.get(key, [])
        merged = []
        # 以原有条数为准：模型少返回就保留旧条目，多返回就追加；不截断
        for i in range(max(len(old_items), len(new_items))):
            item = new_items[i] if i < len(new_items) and isinstance(new_items[i], dict) else {}
            base = dict(old_items[i]) if i < len(old_items) else {}
            for field in ("date", "school", "major", "degree", "gpa", "extra", "courses",
                          "company", "dept", "role", "org"):
                if item.get(field):
                    base[field] = item[field]
            para = _as_paragraph(item) if item else ""
            if para:
                base["bullets"] = [para if para.endswith("。") else para + "。"]
            if base:
                merged.append(base)
        out[key] = merged
    if raw.get("skills"):
        out["skills"] = [str(x).strip() for x in raw["skills"] if str(x).strip()]
    # 段落版：每段最多 1 条；旧数据若有多条，合并成一段
    for key in ("internships", "campus"):
        for item in out.get(key, []):
            bullets = item.get("bullets") or []
            if len(bullets) > 1:
                item["bullets"] = [_clean_para("；".join(str(b) for b in bullets)) + "。"]
    out["_format"] = "paragraph"
    return out


def _warnings(profile: dict[str, Any], source: str) -> list[str]:
    warns = []
    for key in ("internships", "campus"):
        for item in profile.get(key, []):
            for b in item.get("bullets", []):
                for num in re.findall(r"\d+(?:\.\d+)?%?", str(b)):
                    if num not in source:
                        warns.append(f"“{num}”在原文中没找到：{str(b)[:60]}")
    return warns[:10]


def _secret(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:  # noqa: BLE001
        return None


def _call_api(direction: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    key = _secret("DEEPSEEK_API_KEY") or _secret("OPENAI_API_KEY")
    if not key:
        return None
    if _secret("DEEPSEEK_API_KEY"):
        base = _secret("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        model = _secret("DEEPSEEK_MODEL") or "deepseek-chat"
    else:
        base = _secret("OPENAI_BASE_URL") or ""
        model = _secret("OPENAI_MODEL") or "gpt-4o-mini"
    if not base:
        return None
    url = base.rstrip("/") + "/chat/completions"
    template = PROMPT_PATH.read_text(encoding="utf-8") if PROMPT_PATH.exists() else (
        "按方向 {{direction}} 整理四段，不编造。只输出 JSON。\n{{profile_json}}"
    )
    prompt = template.replace("{{direction}}", direction).replace(
        "{{profile_json}}", json.dumps(_compact(profile), ensure_ascii=False, indent=2)
    )
    messages = [
        {"role": "system", "content": "你只输出合法 JSON，不要 Markdown，不要解释。"},
        {"role": "user", "content": prompt},
    ]
    import requests

    def call(use_json_mode: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "temperature": 0, "max_tokens": 3000, "messages": messages}
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|```$", "", content, flags=re.S).strip()
        return json.loads(content)

    try:
        try:
            return call(True)
        except Exception:  # noqa: BLE001
            return call(False)
    except Exception:  # noqa: BLE001
        return None


def rule_tailor(profile: dict[str, Any], direction: str) -> dict[str, Any]:
    out = copy.deepcopy(profile)
    out["direction"] = direction
    out["job_intent"] = direction
    out["_format"] = "paragraph"
    for key in ("internships", "campus"):
        for item in out.get(key, []):
            text = _as_paragraph(item).rstrip("。")
            item["bullets"] = [text + "。"] if text else []
    return out


def tailor_profile(profile: dict[str, Any], direction: str) -> tuple[dict[str, Any], str, list[str]]:
    raw = _call_api(direction, profile)
    if not raw:
        return rule_tailor(profile, direction), "rule", []
    out = _normalize(profile, raw)
    out["direction"] = direction
    out["job_intent"] = direction
    out["_format"] = "paragraph"
    warns = _warnings(out, _source_text(profile))
    out["_tailor_warnings"] = warns
    return out, "llm", warns
