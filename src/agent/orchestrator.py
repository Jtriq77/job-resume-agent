"""Agent 编排器：先规划，再逐步执行，每步发出可观察事件。

当前是“可运行骨架”：
- 真实模式：缺数据/模型/模板的步骤会明确标记 skipped，不伪造结果；
- demo 模式：用样例数据跑通完整事件流，供前端联调与演示，事件里带 demo=True。
"""

from __future__ import annotations

import csv
import json
import os
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

try:
    from .events import AgentEvent, EventBus, Status, new_run_id, now_iso
except ImportError:  # 允许直接以脚本方式导入
    from events import AgentEvent, EventBus, Status, new_run_id, now_iso


@dataclass(frozen=True)
class StepSpec:
    step_id: str
    title: str
    why: str
    tool: str
    model: str = ""
    human_gate: bool = False


DEMO_DURATIONS = {
    "plan": 120, "intake": 180, "normalize": 2600, "load_jobs": 320,
    "classify_family": 920, "rank_jobs": 780, "group_tiers": 210,
    "check_links": 1600, "tailor_resume": 3200, "verify_facts": 900,
    "export": 1200, "track": 80,
}

PIPELINE: list[StepSpec] = [
    StepSpec("intake", "校验散装信息", "先确认必填项，避免后面用错数据", "schema_validator"),
    StepSpec("normalize", "结构化画像", "把散装文本归一成事实库，后续生成只引用事实", "llm_extract", "文本模型"),
    StepSpec("load_jobs", "加载岗位库", "按城市/方向取候选，缩小排序范围", "sqlite"),
    StepSpec("classify_family", "岗位族分类", "判断岗位方向，用于筛选、冷启动和岗位地图", "tfidf_svm", "TF-IDF + LinearSVC"),
    StepSpec("rank_jobs", "匹配排序", "用 ML 给候选打分，决定先看哪些、投哪些", "logreg_ranker", "LR + BGE"),
    StepSpec("group_tiers", "三档分组", "按公司表组织成冲刺/匹配/保底，便于执行", "tier_rule"),
    StepSpec("check_links", "链接核验", "确认链接可用，失效时走公司主页兜底", "http_checker"),
    StepSpec("tailor_resume", "定制简历", "按 JD 重排事实与关键词，不改事实", "docx_template", "python-docx"),
    StepSpec("verify_facts", "事实校验", "拦截编造的数字/公司/时间，守住真实性", "fact_checker", "rule + LLM"),
    StepSpec("export", "导出投递包", "生成 DOCX/PDF/打招呼语，供用户确认", "exporter"),
    StepSpec("track", "记录已投", "记录渠道、时间、状态，支持跟进", "sqlite"),
]


def _get(d: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


class ResumeAgent:
    def __init__(
        self,
        root: str | Path,
        demo_mode: bool = False,
        on_event: Any | None = None,
    ):
        self.root = Path(root).resolve()
        self.demo = demo_mode
        self.bus = EventBus(new_run_id(), on_event=on_event)
        self.artifacts: dict[str, Any] = {}

    @property
    def run_id(self) -> str:
        return self.bus.run_id

    def run(self, payload: dict[str, Any]) -> Iterator[AgentEvent]:
        yield self._plan_event()
        for spec in PIPELINE:
            yield self._running_event(spec)
            started = time.perf_counter()
            try:
                result = self._execute(spec, payload)
                actual_ms = int((time.perf_counter() - started) * 1000)
                duration = DEMO_DURATIONS.get(spec.step_id, actual_ms) if self.demo else actual_ms
                event = self._finish_event(spec, result, duration)
            except Exception as exc:  # noqa: BLE001 - 需要把失败暴露给前端
                duration = int((time.perf_counter() - started) * 1000)
                event = self._error_event(spec, exc, duration)
            yield event

    # ---------- events ----------

    def _plan_event(self) -> AgentEvent:
        steps = [
            {"step_id": s.step_id, "title": s.title, "why": s.why, "tool": s.tool}
            for s in PIPELINE
        ]
        return self.bus.emit(
            AgentEvent(
                run_id=self.run_id,
                seq=self.bus.next_seq(),
                step_id="plan",
                title="制定执行计划",
                status=Status.DONE,
                why="先规划这次要做哪些步骤，再逐步执行；输入不足时只跑必要步骤",
                tool="planner",
                input_summary="用户画像 + 目标城市/方向",
                output_summary=f"计划 {len(steps)} 步",
                detail={"steps": steps, "demo": self.demo},
                confidence=0.9,
                started_at=now_iso(),
                ended_at=now_iso(),
                duration_ms=0,
            )
        )

    def _running_event(self, spec: StepSpec) -> AgentEvent:
        return self.bus.emit(
            AgentEvent(
                run_id=self.run_id,
                seq=self.bus.next_seq(),
                step_id=spec.step_id,
                title=spec.title,
                status=Status.RUNNING,
                why=spec.why,
                tool=spec.tool,
                model=spec.model,
                human_gate=spec.human_gate,
                started_at=now_iso(),
                detail={"demo": self.demo},
            )
        )

    def _finish_event(self, spec: StepSpec, result: dict[str, Any], duration: int) -> AgentEvent:
        return self.bus.emit(
            AgentEvent(
                run_id=self.run_id,
                seq=self.bus.next_seq(),
                step_id=spec.step_id,
                title=spec.title,
                status=result.get("status", Status.DONE),
                why=spec.why,
                tool=spec.tool,
                model=spec.model,
                input_summary=result.get("input_summary", ""),
                output_summary=result.get("output_summary", ""),
                detail={**result.get("detail", {}), "demo": self.demo},
                confidence=result.get("confidence"),
                retry_count=result.get("retry_count", 0),
                human_gate=spec.human_gate,
                started_at=now_iso(),
                ended_at=now_iso(),
                duration_ms=duration,
                error=result.get("error"),
            )
        )

    def _error_event(self, spec: StepSpec, exc: Exception, duration: int) -> AgentEvent:
        return self.bus.emit(
            AgentEvent(
                run_id=self.run_id,
                seq=self.bus.next_seq(),
                step_id=spec.step_id,
                title=spec.title,
                status=Status.ERROR,
                why=spec.why,
                tool=spec.tool,
                model=spec.model,
                input_summary="",
                output_summary="步骤失败，已记录错误；可重试或回退",
                detail={"demo": self.demo, "exception_type": type(exc).__name__},
                human_gate=spec.human_gate,
                started_at=now_iso(),
                ended_at=now_iso(),
                duration_ms=duration,
                error=str(exc),
            )
        )

    # ---------- execution ----------

    def _execute(self, spec: StepSpec, payload: dict[str, Any]) -> dict[str, Any]:
        if self.demo:
            return self._execute_demo(spec, payload)
        handler = getattr(self, f"_real_{spec.step_id}", None)
        if handler is None:
            return {
                "status": Status.SKIPPED,
                "output_summary": "该步骤尚未接入",
                "detail": {"reason": "handler not implemented"},
            }
        return handler(payload)

    def _execute_demo(self, spec: StepSpec, payload: dict[str, Any]) -> dict[str, Any]:
        """演示模式：返回带 demo 标记的样例，不用于真实结论。"""
        demo: dict[str, dict[str, Any]] = {
            "intake": {
                "input_summary": "散装信息 1 份",
                "output_summary": "必填项齐全；政治面貌默认不展示；手机/邮箱已脱敏",
                "detail": {"missing": [], "redacted": ["phone", "email"], "facts_count": 9},
                "confidence": 0.95,
            },
            "normalize": {
                "input_summary": "散装文本约 600 字",
                "output_summary": "抽取 9 条事实（教育 1 / 实习 2 / 项目 2 / 竞赛 2 / 技能 2）",
                "detail": {
                    "facts": [
                        {"fact_id": "edu_01", "type": "education", "text": "某211 信息管理 本科"},
                        {"fact_id": "int_01_b1", "type": "internship", "text": "电商公司数据分析实习"},
                        {"fact_id": "proj_01", "type": "project", "text": "用户流失预测项目"},
                    ]
                },
                "confidence": 0.89,
            },
            "load_jobs": {
                "input_summary": "城市=上海，方向=数据分析/产品/运营",
                "output_summary": "命中 128 条候选（校招 76 / 实习 32 / 社招 20）",
                "detail": {"sql": "select ... where city in (...) and category in (...)", "candidates": 128},
                "confidence": 1.0,
            },
            "classify_family": {
                "input_summary": "128 条 JD 标题+正文",
                "output_summary": "产品 31 / 技术 58 / 运营 25 / 未分类 14；平均置信度 0.91",
                "detail": {
                    "distribution": {"产品": 31, "技术": 58, "运营": 25, "未分类": 14},
                    "low_confidence_examples": ["j041 数据运营（产品/运营边界）"],
                    "gold_macro_f1": "待实验",
                },
                "confidence": 0.91,
            },
            "rank_jobs": {
                "input_summary": "画像 r01 × 128 条候选",
                "output_summary": "Top-10；最高 0.82，最低 0.41；3 条低置信度转人工",
                "detail": {
                    "top_k": [
                        {"job_id": "j001", "title": "数据分析师（校招）", "score": 0.82},
                        {"job_id": "j014", "title": "商业分析（实习）", "score": 0.77},
                        {"job_id": "j031", "title": "产品运营（校招）", "score": 0.71},
                    ],
                    "features": {"skill_cov": 0.71, "bge_cos": 0.63, "edu_match": 1.0},
                },
                "confidence": 0.78,
            },
            "group_tiers": {
                "input_summary": "Top-15 + 公司分层表",
                "output_summary": "大厂 5 / 中厂 5 / 小厂 5；2 家公司未分层",
                "detail": {"tiers": {"大厂": 5, "中厂": 5, "小厂": 5}, "unassigned": 2},
                "confidence": 0.86,
            },
            "check_links": {
                "input_summary": "15 条岗位链接",
                "output_summary": "ok 12 / login_required 2 / dead 1；死链已切公司主页",
                "detail": {
                    "status": {"ok": 12, "login_required": 2, "dead": 1},
                    "fallback_example": {"job_id": "j007", "from": "深链", "to": "career_url"},
                },
                "confidence": 0.8,
            },
            "tailor_resume": {
                "input_summary": "基础简历 + j001 JD",
                "output_summary": "重排 6 条 bullet，补 3 个关键词，未新增事实",
                "detail": {"bullets_changed": 6, "keywords_added": ["SQL", "AB 测试", "用户增长"]},
                "confidence": 0.84,
                "human_gate": True,
            },
            "verify_facts": {
                "input_summary": "6 条改写 bullet",
                "output_summary": "5 条通过，1 条拦截（出现原文没有的“提升 30%”）",
                "detail": {"passed": 5, "blocked": 1, "blocked_text": "将转化率提升 30%"},
                "confidence": 0.93,
            },
            "export": {
                "input_summary": "定制简历 JSON",
                "output_summary": "生成 resume_j001.docx / resume_j001.pdf / greeting.txt",
                "detail": {"files": ["resume_j001.docx", "resume_j001.pdf", "greeting.txt"]},
                "confidence": 0.99,
            },
            "track": {
                "input_summary": "job_id=j001",
                "output_summary": "已投记录 a001；7 天后跟进提醒已设置",
                "detail": {"app_id": "a001", "status": "已投", "channel": "公司校招官网"},
                "confidence": 1.0,
            },
        }
        item = demo.get(spec.step_id)
        if item is None:
            return {"status": Status.SKIPPED, "output_summary": "无演示数据", "detail": {}}
        return {"status": Status.DONE, **item}

    # ---------- real handlers（逐步接入） ----------

    def _real_intake(self, payload: dict[str, Any]) -> dict[str, Any]:
        required = {
            "姓名": _get(payload, "basic.name"),
            "手机": _get(payload, "basic.phone"),
            "邮箱": _get(payload, "basic.email"),
            "教育经历": payload.get("education"),
            "技能": payload.get("skills"),
        }
        missing = [k for k, v in required.items() if not v]
        return {
            "status": Status.DONE if not missing else Status.WAITING_HUMAN,
            "input_summary": "散装信息 1 份",
            "output_summary": "必填项齐全" if not missing else f"缺 {len(missing)} 项：{', '.join(missing)}",
            "detail": {"missing": missing},
            "confidence": 1.0 if not missing else 0.5,
        }

    def _real_normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
            return {
                "status": Status.SKIPPED,
                "output_summary": "未配置 LLM API，抽取器待接入",
                "detail": {"reason": "no_api_key"},
            }
        return {
            "status": Status.SKIPPED,
            "output_summary": "抽取器待接入（下一步实现）",
            "detail": {"reason": "extractor_not_implemented"},
        }

    def _real_load_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.root / "data" / "jobs_linked.jsonl"
        if not path.exists():
            return {
                "status": Status.SKIPPED,
                "output_summary": "岗位库尚未生成",
                "detail": {"expected": str(path)},
            }
        raw_jobs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        target_cities = _get(payload, "basic.target_cities", []) or []
        target_families = _get(payload, "basic.job_intent", []) or []
        jobs = raw_jobs
        if target_cities:
            city_jobs = [j for j in jobs if set(j.get("cities", [])) & set(target_cities)]
            # 少于 5 条时不强行过滤，避免演示集被筛空
            jobs = city_jobs if len(city_jobs) >= 5 else jobs
        if target_families:
            cats: set[str] = set()
            for f in target_families:
                if f in ("产品经理", "产品运营"):
                    cats.add("产品")
                if f in ("产品运营", "运营", "用户增长"):
                    cats.add("运营")
                if f in ("数据分析", "算法"):
                    cats.update(["技术", "产品"])
            filtered = [j for j in jobs if j.get("category") in cats]
            if len(filtered) >= 5:
                jobs = filtered
        self.artifacts["jobs"] = jobs
        return {
            "status": Status.DONE,
            "input_summary": f"城市={target_cities} 方向={target_families}",
            "output_summary": f"加载 {len(jobs)} 条岗位（来源 {path.name}）",
            "detail": {"count": len(jobs), "file": str(path)},
            "confidence": 1.0,
        }

    def _real_classify_family(self, payload: dict[str, Any]) -> dict[str, Any]:
        model_path = self.root / "models" / "family_clf.pkl"
        jobs = self.artifacts.get("jobs", [])
        if not model_path.exists():
            return {
                "status": Status.SKIPPED,
                "output_summary": "岗位族分类模型尚未训练",
                "detail": {"expected": str(model_path)},
            }
        if not jobs:
            return {"status": Status.SKIPPED, "output_summary": "没有候选岗位可分类", "detail": {}}
        from src.ml.text_clf import TfidfNB
        model = TfidfNB.load(model_path)
        preds, confs, correct = [], [], 0
        for j in jobs:
            label, conf, _ = model.predict_one(str(j.get("title", "")), str(j.get("jd_text", "")))
            j["predicted_family"] = label
            j["family_confidence"] = conf
            preds.append(label)
            confs.append(conf)
            if j.get("category") and label == j["category"]:
                correct += 1
        dist = Counter(preds)
        labeled = [j for j in jobs if j.get("category")]
        acc = correct / len(labeled) if labeled else None
        return {
            "status": Status.DONE,
            "input_summary": f"{len(jobs)} 条岗位（标题+JD）",
            "output_summary": " / ".join(f"{k} {v}" for k, v in dist.most_common()) + f"；平均置信度 {sum(confs)/len(confs):.2f}" + (f"；与规则标签一致率 {acc:.2f}" if acc is not None else ""),
            "detail": {"distribution": dict(dist), "avg_confidence": round(sum(confs)/len(confs), 3), "agreement_with_rule_label": round(acc, 3) if acc is not None else None},
            "confidence": round(sum(confs)/len(confs), 3),
        }

    def _real_rank_jobs(self, payload: dict[str, Any]) -> dict[str, Any]:
        jobs = self.artifacts.get("jobs", [])
        if not jobs:
            return {"status": Status.SKIPPED, "output_summary": "没有候选岗位可排序", "detail": {}}
        from src.ml.baseline_ranker import SkillBaselineRanker
        edu = "本科"
        if isinstance(payload.get("education"), list) and payload["education"]:
            first_edu = payload["education"][0]
            if isinstance(first_edu, dict):
                edu = first_edu.get("degree", "本科")
        profile = {
            "skills": payload.get("skills") or [],
            "job_intent": _get(payload, "basic.job_intent", []) or [],
            "target_cities": _get(payload, "basic.target_cities", []) or [],
            "degree": edu,
        }
        ranker = SkillBaselineRanker()
        ranked = ranker.rank(profile, jobs, top_k=10)
        self.artifacts["ranked_jobs"] = ranked
        top3 = "；".join(f"{r['title'][:18]} {r['score']:.2f}" for r in ranked[:3])
        return {
            "status": Status.DONE,
            "input_summary": f"画像技能 {len(profile['skills'])} 个 × 候选 {len(jobs)} 条",
            "output_summary": f"Top-{len(ranked)}；{top3}" if ranked else "无结果",
            "detail": {
                "tool_note": "baseline：技能覆盖+标题+城市/学历规则，不是最终 ML 排序",
                "top_k": [{"job_id": r["job_id"], "title": r["title"], "score": r["score"], "matched_skills": r["matched_skills"]} for r in ranked],
            },
            "confidence": 0.6,
        }

    def _real_group_tiers(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.root / "data" / "companies.csv"
        if not path.exists():
            return {"status": Status.SKIPPED, "output_summary": "公司分层表尚未生成", "detail": {"expected": str(path)}}
        ranked = self.artifacts.get("ranked_jobs", [])
        if ranked:
            counts = Counter(j.get("tier", "未分层") for j in ranked)
            return {
                "status": Status.DONE,
                "output_summary": " / ".join(f"{k} {v}" for k, v in counts.items()),
                "detail": {"tiers": dict(counts), "source": "ranked_jobs"},
            }
        counts = {}
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                counts[row.get("tier", "未分层")] = counts.get(row.get("tier", "未分层"), 0) + 1
        return {
            "status": Status.DONE,
            "output_summary": " / ".join(f"{k} {v}" for k, v in counts.items()),
            "detail": {"tiers": counts, "source": "companies.csv"},
        }

    def _real_check_links(self, payload: dict[str, Any]) -> dict[str, Any]:
        path = self.root / "data" / "link_status.csv"
        if not path.exists():
            return {"status": Status.SKIPPED, "output_summary": "链接尚未核验", "detail": {"expected": str(path)}}
        counts: dict[str, int] = {}
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = row.get("status", "unknown")
                counts[key] = counts.get(key, 0) + 1
        return {"status": Status.DONE, "output_summary": " / ".join(f"{k} {v}" for k, v in counts.items()), "detail": {"status": counts}}

    def _real_tailor_resume(self, payload: dict[str, Any]) -> dict[str, Any]:
        templates = list((self.root / "templates").glob("*.docx"))
        if not templates:
            return {
                "status": Status.SKIPPED,
                "output_summary": "等待你放入 DOCX 模板",
                "detail": {"expected_dir": str(self.root / "templates")},
            }
        return {"status": Status.SKIPPED, "output_summary": "模板解析与渲染待接入", "detail": {"templates": [p.name for p in templates]}}

    def _real_verify_facts(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": Status.SKIPPED, "output_summary": "事实校验待接入", "detail": {}}

    def _real_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": Status.SKIPPED, "output_summary": "导出器待接入", "detail": {}}

    def _real_track(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"status": Status.SKIPPED, "output_summary": "投递追踪待接入", "detail": {}}
