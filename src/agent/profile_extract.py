"""从一段中文自我介绍中抽取简历画像。

优先用 LLM（配置 DEEPSEEK_API_KEY / OPENAI_API_KEY 时）；
没有 key 时用规则抽取 + 追问，保证离线可用。
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """轻量读取项目根目录 .env，避免额外依赖。"""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

CITIES = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州", "西安",
    "长沙", "重庆", "天津", "合肥", "厦门", "无锡", "青岛", "郑州", "济南", "东莞",
]

POLITICAL = ["中共预备党员", "中共党员", "共青团员", "群众", "党员"]

SKILL_HINTS = ["SQL", "Python", "Excel", "Tableau", "Power BI", "R", "Java", "C++", "SPSS",
               "A/B 测试", "AB 测试", "数据分析", "数据可视化", "机器学习", "Pandas", "Numpy"]


def _blank() -> dict[str, Any]:
    return {
        "name": "", "age": "", "political_status": "不展示",
        "phone": "", "email": "", "city": "",
        "target_cities": [], "job_intent": "", "availability": "",
        "contact": "",
        "educations": [], "internships": [], "campus": [], "skills": [],
        "_no_internship": False, "_no_campus": False,
    }


def _find(pattern: str, text: str, flags: int = 0) -> str:
    m = re.search(pattern, text, flags)
    return (m.group(1) if m and m.groups() else "").strip()


def _dates(text: str) -> list[str]:
    # 只认 . / 年 作为年月分隔，避免把 2022.09-2026.06 的 "-" 误读成日期的一部分
    raw = re.findall(r"20\d{2}[./年]\d{1,2}(?:[./月]\d{1,2})?", text)
    out = []
    for d in raw:
        d = d.replace("年", ".").replace("月", "").replace("/", ".")
        parts = d.split(".")
        if len(parts) >= 2:
            out.append(".".join(parts[:3]))
    # 去重保序
    seen, uniq = set(), []
    for d in out:
        if d not in seen:
            seen.add(d)
            uniq.append(d)
    return uniq


def _split_items(text: str) -> list[str]:
    text = re.sub(r"^[：:\s]+", "", text)
    parts = re.split(r"[、，,；;/]+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 1]


def rule_extract(text: str) -> dict[str, Any]:
    p = _blank()
    text = text.replace("\r\n", "\n")

    # 姓名
    for pat in [r"我叫([\u4e00-\u9fa5]{2,4})", r"姓名[：:\s]*([\u4e00-\u9fa5]{2,4})",
                r"我是([\u4e00-\u9fa5]{2,4})(?=[，,。\s]|$)"]:
        name = _find(pat, text)
        if name and not any(x in name for x in ["大学", "学院", "专业", "公司", "实习"]):
            p["name"] = name
            break

    p["phone"] = _find(r"(1[3-9]\d{9}|1[3-9]\d{2}\*{4}\d{4})", text)
    p["email"] = _find(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    p["age"] = _find(r"(\d{2})\s*岁", text)

    if "团员" in text:
        p["political_status"] = "共青团员"
    else:
        for pol in POLITICAL:
            if pol in text:
                p["political_status"] = "中共党员" if pol == "党员" else pol
                break

    p["city"] = next((c for c in CITIES if c in text), "")
    p["target_cities"] = [c for c in CITIES if c in text][:2]

    p["job_intent"] = _find(r"(?:求职意向|想找|目标岗位|投递|应聘)[：:\s]*([^。\n，,；;]+)", text)
    p["availability"] = _find(r"((?:可)?(?:实习|到岗)\s*\d+\s*天(?:/周)?[^。\n，,]*)", text)

    # 教育
    school = _find(r"([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:大学|学院|学校))", text)
    school = re.sub(r"^(我是|我在|就读于|毕业于)", "", school).strip()
    major = _find(r"([\u4e00-\u9fa5]{2,15}(?:专业|系))", text)
    major = re.sub(r"(专业|系)$", "", major).strip()
    major = re.sub(r"^(大学|学院|学校)", "", major).strip()
    degree = next((d for d in ["博士", "硕士", "研究生", "本科", "大专"] if d in text), "")
    if degree == "研究生":
        degree = "硕士"
    dates = _dates(text)
    courses = _find(r"(?:课程|主修)[：:\s]*([^。\n]+)", text)
    # 教育背景只放奖学金等教育相关荣誉；竞赛/比赛/社团归到“校园与项目经历”
    award_parts = []
    for sent in re.split(r"[。\n；;]", text):
        for part in re.split(r"[，,]", sent):
            if "奖学金" in part:
                award_parts.append(part.strip())
    awards = "；".join(award_parts)[:200]
    if school or major:
        p["educations"].append({
            "date": "-".join(dates[:2]) if len(dates) >= 2 else (dates[0] if dates else ""),
            "school": school,
            "major": major,
            "degree": degree,
            "gpa": _find(r"(?:GPA|绩点)[：:\s]*([\d.]+\s*/\s*[\d.]+[^。\n，,]*)", text),
            "extra": awards,
            "courses": courses[:120],
        })

    # 技能
    skill_text = _find(r"(?:技能|熟悉|掌握|会用)[：:\s]*([^。\n]+)", text)
    skills = []
    for s in _split_items(skill_text):
        if 1 <= len(s) <= 20 and s not in skills:
            skills.append(s)
    for hint in SKILL_HINTS:
        if hint.lower() in text.lower() and hint not in skills:
            skills.append(hint)
    p["skills"] = skills

    # 实习 / 项目：按句子切
    for sentence in re.split(r"[。\n；;]", text):
        s = sentence.strip()
        if not s:
            continue
        if "实习" in s and "无实习" not in s and "没有实习" not in s:
            ds = _dates(s)
            company = _find(r"(?:在|于)([\u4e00-\u9fa5A-Za-z0-9]{2,25}?)(?:公司|集团|科技|银行|事务所)?(?:做|担任|实习)", s)
            role = _find(r"(?:做|担任|岗位是|职位是)([\u4e00-\u9fa5A-Za-z0-9]{2,20}?)(?:实习|工作|，|,|$)", s)
            parts = re.split(r"[，,]", s)
            bullets = [x.strip() for x in parts[1:] if len(x.strip()) > 6]
            if not bullets:
                bullets = [s[:80]]
            if company or role:
                p["internships"].append({
                    "date": "-".join(ds[:2]) if len(ds) >= 2 else (ds[0] if ds else ""),
                    "company": company,
                    "dept": "",
                    "role": role,
                    "bullets": bullets,
                })
        elif any(k in s for k in ["项目", "竞赛", "比赛", "社团", "学生会", "获奖"]):
            ds = _dates(s)
            org = _find(r"([\u4e00-\u9fa5A-Za-z0-9]{2,25}(?:项目|竞赛|比赛|社团|学生会))", s) or s[:24]
            org = re.sub(r"^(我还?做了|我做了|做了|完成的|参与的|参加了|我还)", "", org).strip()
            parts = re.split(r"[，,]", s)
            bullets = [x.strip() for x in parts[1:] if len(x.strip()) > 6]
            p["campus"].append({
                "date": "-".join(ds[:2]) if len(ds) >= 2 else (ds[0] if ds else ""),
                "org": org,
                "role": "",
                "bullets": bullets or [s[:80]],
            })

    # 不截断：用户提到几段就保留几段
    p["contact"] = build_contact(p)
    return p


def build_contact(p: dict[str, Any]) -> str:
    parts = [p.get("phone", ""), p.get("email", ""), p.get("city", "")]
    if p.get("age"):
        parts.append(f"{p['age']}岁")
    if p.get("political_status") and p["political_status"] != "不展示":
        parts.append(f"政治面貌：{p['political_status']}")
    if p.get("availability"):
        parts.append(p["availability"])
    return " | ".join(x for x in parts if x)


def merge(base: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for k, v in new.items():
        if k.startswith("_"):
            if v:
                out[k] = True
            continue
        if k in ("educations", "internships", "campus", "skills"):
            existing = out.get(k, [])
            for item in v or []:
                key = str(item) if isinstance(item, str) else json.dumps(item, sort_keys=True, ensure_ascii=False)
                if key not in [str(x) if isinstance(x, str) else json.dumps(x, sort_keys=True, ensure_ascii=False) for x in existing]:
                    existing.append(item)
            out[k] = existing
        elif isinstance(v, list):
            if v:
                out[k] = v
        elif k == "political_status":
            if v and v != "不展示":
                out[k] = v
        elif v not in ("", None, "不展示"):
            out[k] = v
    out["contact"] = build_contact(out)
    return out


SCHOLARSHIP_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{0,15}奖学金)")
COMPETITION_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:竞赛|比赛|大赛)|[\u4e00-\u9fa5A-Za-z0-9]{2,12}杯)")
DATE_RANGE_RE = re.compile(
    r"(20\d{2})\s*[年./-]\s*(\d{1,2})\s*月?\s*(?:到|至|~|-)\s*(20\d{2})\s*[年./-]\s*(\d{1,2})\s*月?"
)


def _scholarship_names(text: str) -> list[str]:
    names: list[str] = []
    for clause in re.split(r"[。；;\n，,]", text):
        if "奖学金" not in clause:
            continue
        for seg in re.split(r"以及|和|及|、", clause):
            if "奖学金" not in seg:
                continue
            seg = re.sub(r"^(还|也|又|曾|获得|荣获|拿过|有|多次|连续|我)+", "", seg.strip())
            m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]{2,10}奖学金)", seg)
            if m:
                name = m.group(1)
                if name != "奖学金" and name not in names:
                    names.append(name)
    return names


def apply_supplement(profile: dict[str, Any], text: str) -> tuple[dict[str, Any], list[str]]:
    """兜底解析补充信息：奖学金→教育荣誉，竞赛→校园与项目，技能→技能特长，日期→补空日期。

    模型对“我有上海市奖学金”这类单句经常返回空四段，所以在合并后做一层确定性补写。
    """
    out = json.loads(json.dumps(profile, ensure_ascii=False))
    added: list[str] = []
    educations = out.get("educations", [])
    campus = out.get("campus", [])
    skills = out.get("skills", [])

    # 1) 奖学金：追加到第一段教育（通常是最新/最高学历）的 extra
    for name in _scholarship_names(text):
        if len(name) < 4 or name in ("奖学金",):
            continue
        existing_extra = "；".join(str(e.get("extra", "")) for e in educations)
        if name in existing_extra:
            continue
        if educations:
            # 优先挂到最高学历（硕士/博士），否则第一段
            e = next((x for x in educations if str(x.get("degree", "")) in ("硕士", "博士", "研究生")), educations[0])
            e["extra"] = "；".join(x for x in [str(e.get("extra", "")).strip(), name] if x)
        else:
            skills.append("荣誉：" + name)
        added.append(name)

    # 2) 竞赛/比赛：追加到校园与项目经历，按名称去重
    campus_text = " ".join(str(c.get("org", "")) + " " + " ".join(str(b) for b in c.get("bullets", [])) for c in campus)
    for m in COMPETITION_RE.finditer(text):
        name = m.group(1).strip("，。；、 ")
        name = re.sub(r"^(获得|荣获|拿过|参加|在|了|过|还|又|曾|我)+", "", name).strip()
        if not name or name in campus_text or "奖学金" in name:
            continue
        clauses = [x.strip() for x in re.split(r"[，,。；;\n]", text) if name in x]
        bullet = clauses[0] if clauses else f"获得{name}。"
        campus.append({"date": "", "org": name, "role": "", "bullets": [bullet]})
        campus_text += " " + name + " " + bullet
        added.append(name)

    # 3) 技能：已知技能词补进 skills
    for hint in SKILL_HINTS:
        if hint.lower() in text.lower() and hint not in skills:
            skills.append(hint)
            added.append(hint)

    # 4) 日期区间：补到还没日期的实习/项目上
    ranges = []
    for y1, m1, y2, m2 in DATE_RANGE_RE.findall(text):
        ranges.append(f"{int(y1)}.{int(m1):02d}-{int(y2)}.{int(m2):02d}")
    if ranges:
        for it in out.get("internships", []):
            if not it.get("date") and ranges:
                it["date"] = ranges.pop(0)
    # “2027届”只补到最高学历那一行，不臆造起止月
    if educations and not educations[0].get("date") and "2027届" in text:
        educations[0]["date"] = "2027届"

    out["educations"] = educations
    out["campus"] = campus
    out["skills"] = skills
    return out, added


def missing_required(p: dict[str, Any]) -> list[str]:
    miss = []
    if not p.get("name"):
        miss.append("姓名")
    if not p.get("phone"):
        miss.append("手机")
    if not p.get("email"):
        miss.append("邮箱")
    edu = (p.get("educations") or [{}])[0]
    if not edu.get("school"):
        miss.append("学校")
    if not edu.get("major"):
        miss.append("专业")
    return miss


def next_question(p: dict[str, Any]) -> str:
    miss = missing_required(p)
    if miss:
        return "我还差这些必填项：" + "、".join(miss) + "。你可以直接补一句，比如「手机 138xxxx，邮箱 xx@xx.com」。"
    if not p.get("job_intent"):
        return "你的求职意向是什么？比如「数据分析」「产品运营」「算法」。"
    if not p.get("internships") and not p.get("_no_internship"):
        return "基本信息齐了。你有实习吗？按「时间 + 公司 + 岗位 + 做了什么」发我一段；没有就回「没有实习」。"
    if not p.get("_skip_dates"):
        for it in p.get("internships", []):
            if not it.get("date"):
                return f"{it.get('company') or '这段实习'} 的时间是哪到哪？例如「2025.03-2025.08」。不记得就回「不记得」。"
    if not p.get("campus") and not p.get("_no_campus"):
        return "有项目、竞赛或校园经历吗？按「时间 + 名称 + 你做了什么 + 结果」发我；没有就回「没有项目」。"
    if not p.get("_skip_dates"):
        for it in p.get("campus", []):
            if not it.get("date"):
                return f"{it.get('org') or '这个项目'} 的时间？例如「2025.09-2025.12」。不记得就回「不记得」。"
    return "信息够了，可以点下面「用这份画像生成简历」；也可以继续补充竞赛、证书或量化成果。"


def summary(p: dict[str, Any]) -> str:
    edu = (p.get("educations") or [{}])[0]
    lines = [
        f"姓名：{p.get('name') or '—'}",
        f"联系方式：{p.get('contact') or '—'}",
        f"学校/专业：{edu.get('school') or '—'} / {edu.get('major') or '—'}（{edu.get('degree') or '—'}）",
        f"技能：{'、'.join(p.get('skills', [])) or '—'}",
        f"实习：{len(p.get('internships', []))} 段；项目/校园：{len(p.get('campus', []))} 段",
    ]
    return "\n".join(lines)


def _normalize_llm(data: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    # 兼容模型可能输出的同义 key
    if "education" in data and "educations" not in data:
        data["educations"] = data.pop("education")
    if "projects" in data and "campus" not in data:
        data["campus"] = data.pop("projects")
    if "campus_projects" in data and "campus" not in data:
        data["campus"] = data.pop("campus_projects")
    scalar = ["name", "age", "political_status", "phone", "email", "city", "job_intent", "availability"]
    for k in scalar:
        out[k] = str(data.get(k) or "").strip()
    out["target_cities"] = [str(x).strip() for x in (data.get("target_cities") or []) if str(x).strip()][:2]
    out["educations"] = data.get("educations") or []
    out["internships"] = data.get("internships") or []
    out["campus"] = data.get("campus") or []
    out["skills"] = [str(x).strip() for x in (data.get("skills") or []) if str(x).strip()]
    for key in ("educations", "internships", "campus"):
        for item in out[key]:
            if not isinstance(item, dict):
                continue
            if key != "educations":
                item["bullets"] = [str(b).strip() for b in item.get("bullets", []) if str(b).strip()]
    return out


def _warnings(data: dict[str, Any], text: str) -> list[str]:
    warns: list[str] = []
    for section in ("internships", "campus"):
        for item in data.get(section, []):
            if not isinstance(item, dict):
                continue
            for b in item.get("bullets", []):
                for num in re.findall(r"\d+(?:\.\d+)?%?", str(b)):
                    if num not in text:
                        warns.append(f"“{num}”在原文中没找到：{str(b)[:50]}")
    for e in data.get("educations", []):
        school = str(e.get("school") or "")
        if school and school not in text:
            warns.append(f"学校“{school}”在原文中没找到")
    for it in data.get("internships", []):
        company = str(it.get("company") or "")
        if company and company not in text:
            warns.append(f"公司“{company}”在原文中没找到")
    return warns[:10]


def _fill_missing(primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(primary, ensure_ascii=False))
    for k, v in fallback.items():
        if k in ("educations", "internships", "campus", "skills"):
            if not out.get(k) and v:
                out[k] = v
        elif not out.get(k):
            out[k] = v
    return out


def _secret(name: str) -> str | None:
    """本地读环境变量；云端优先读 Streamlit secrets。"""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        return st.secrets.get(name)
    except Exception:  # noqa: BLE001
        return None


def llm_extract(text: str) -> dict[str, Any] | None:
    """用文本模型的 OpenAI 兼容接口做四段抽取；失败返回 None。"""
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
    prompt_path = ROOT / "skills" / "resume-section-extractor" / "prompt.md"
    base_prompt = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else (
        "从这段中文自我介绍抽取四段 JSON：educations, internships, campus, skills。未知留空，不要编造。"
    )
    prompt = base_prompt + "\n\n用户原文：\n" + text
    messages = [
        {"role": "system", "content": "你只输出合法 JSON，不要 Markdown 代码块，不要解释。"},
        {"role": "user", "content": prompt},
    ]

    import requests

    def _call(use_json_mode: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "temperature": 0,
            "max_tokens": 2200,
            "messages": messages,
        }
        if use_json_mode:
            payload["response_format"] = {"type": "json_object"}
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=40,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*|```$", "", content, flags=re.S).strip()
        return json.loads(content)

    try:
        try:
            raw = _call(True)
        except Exception:  # noqa: BLE001 - 某些兼容端点不支持 json_object，退回普通模式
            raw = _call(False)
        data = _normalize_llm(raw)
        data["contact"] = build_contact({**_blank(), **data})
        data["_warnings"] = _warnings(data, text)
        return data
    except Exception:  # noqa: BLE001
        return None


def extract(text: str) -> tuple[dict[str, Any], str]:
    rule = rule_extract(text)
    llm = llm_extract(text)
    if llm:
        merged = _fill_missing(llm, rule)
        merged["contact"] = build_contact(merged)
        return merged, "llm"
    return rule, "rule"
