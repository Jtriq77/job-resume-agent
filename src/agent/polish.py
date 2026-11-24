"""把口语化的经历整理成简历语言。

原则：
- 只改写，不新增事实、不补造数字；
- 去掉“然后/就是/其实/我/还”等口语；
- 把“做了/弄了/帮忙”改成“完成/协助/参与”等动作；
- 合并短句，按“有数字 > 有动作 > 原始顺序”保留最多 3 条；
- 返回 before/after，方便用户在生成前核对。
"""

from __future__ import annotations

import copy
import re
from typing import Any

PREFIX_FILLERS = r"^(然后|就是|其实|那个|反正|差不多|大概|我觉得|我感觉|我们|我|还|也|另外|接着|同时|以及|后来)+"
ACTION_WORDS = ["负责", "参与", "完成", "协助", "设计", "搭建", "分析", "推动", "输出",
                "组织", "主导", "使用", "通过", "优化", "撰写", "跟进", "协调", "策划", "写"]


def _clean_clause(text: str) -> str:
    text = text.strip("，,。；;、 \n\t")
    text = re.sub(PREFIX_FILLERS, "", text)
    text = text.replace("我负责", "负责").replace("负责了", "负责")
    text = text.replace("主要是负责", "负责").replace("主要是", "")
    text = text.replace("我做了", "完成").replace("做了", "完成")
    text = text.replace("弄了", "完成").replace("搞了", "完成")
    text = text.replace("帮忙", "协助").replace("参加了", "参与")
    text = text.replace("提升了", "提升").replace("涨了", "增长")
    text = text.replace("后来调了参数", "调整模型参数").replace("调了参数", "调整模型参数")
    text = re.sub(r"^是", "", text)
    text = re.sub(r"主要用\s*", "使用 ", text)
    text = re.sub(r"(?<!使)用\s*(SQL|Python|Excel|Tableau|R)", r"使用 \1", text)
    text = re.sub(r"^做", "参与", text)
    text = re.sub(r"^跟", "与", text)
    text = re.sub(r"的$", "", text)
    text = re.sub(r"AUC\s*([0-9.]+)", r"AUC \1", text)
    text = re.sub(r"([\u4e00-\u9fff])(\d+(?:\.\d+)?%)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text).strip("，,。；;、 ")
    # 英文/工具词前后留空格，提升可读性
    text = re.sub(r"([\u4e00-\u9fff])(SQL|Python|Excel|Tableau|AB|A/B)", r"\1 \2", text)
    text = re.sub(r"(SQL|Python|Excel|Tableau|AB|A/B)([\u4e00-\u9fff])", r"\1 \2", text)
    return text


def _split(text: str) -> list[str]:
    parts = re.split(r"[。；;\n，,]|然后|还有|另外|接着|同时|以及", text)
    return [p for p in parts if p and p.strip()]


def _starts_action(text: str) -> bool:
    return any(text.startswith(a) for a in ACTION_WORDS)


def _merge_short(out: list[str]) -> list[str]:
    merged: list[str] = []
    for c in out:
        if merged and _starts_action(merged[-1]) and (_starts_action(c) or re.search(r"\d", c)):
            if merged[-1].count("，") < 2 and len(re.sub(r"\W", "", merged[-1] + c)) <= 55:
                merged[-1] = merged[-1].rstrip("。") + "，" + c
                continue
        merged.append(c)
    return merged


def polish_bullets(raw: str | list[str]) -> list[str]:
    if isinstance(raw, list):
        raw = "；".join(str(x) for x in raw)
    clauses = [_clean_clause(x) for x in _split(str(raw))]
    out: list[str] = []
    for c in clauses:
        if not c:
            continue
        # “在 XX 实习/工作”这种，header 已经写了，删掉
        if re.match(r"^(在|于).{1,30}(实习|工作)$", c):
            continue
        if len(re.sub(r"\W", "", c)) < 4 and not re.search(r"\d", c) and not _starts_action(c):
            continue
        if any(k in c for k in ["效果不好", "没做好", "失败了", "不会"]):
            continue
        if c not in out:
            out.append(c)

    out = _merge_short(out)

    if len(out) > 3:
        scored = []
        for i, c in enumerate(out):
            score = 2 if re.search(r"\d", c) else 1 if _starts_action(c) else 0
            scored.append((score, i, c))
        keep = sorted(scored, key=lambda x: (-x[0], x[1]))[:3]
        out = [c for _, _, c in sorted(keep, key=lambda x: x[1])]

    out = [c if c.endswith(("。", "！", "？")) else c + "。" for c in out]
    return out


def _date_key(item: dict[str, Any]) -> tuple[int, int]:
    text = str(item.get("date", ""))
    m = re.search(r"(20\d{2})[.\-/年](\d{1,2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(20\d{2})", text)
    return (int(m.group(1)), 0) if m else (0, 0)


def polish_profile(profile: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    out = copy.deepcopy(profile)
    changes: list[dict[str, str]] = []
    for key, label in [("internships", "实习"), ("campus", "项目/校园")]:
        for item in out.get(key, []):
            before = "；".join(item.get("bullets", []))
            after = polish_bullets(item.get("bullets", []))
            if after:
                item["bullets"] = after
            changes.append({
                "section": label,
                "org": item.get("company") or item.get("org") or "",
                "before": before,
                "after": "；".join(item.get("bullets", [])),
            })
        out[key] = sorted(out.get(key, []), key=_date_key, reverse=True)
    return out, changes
