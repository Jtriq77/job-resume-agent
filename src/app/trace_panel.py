"""板块内嵌 Agent 轨迹：每个 Tab 右侧显示本板块刚执行的步骤。

不再单独占一个「Agent 运行轨迹」Tab。
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import streamlit as st

STATUS = {
    "running": ("◉", "运行中", "#2563eb"),
    "done": ("✓", "完成", "#16a34a"),
    "error": ("✕", "失败", "#dc2626"),
    "waiting_human": ("!", "待确认", "#d97706"),
    "skipped": ("–", "跳过", "#64748b"),
}


def _store() -> dict[str, list[dict[str, Any]]]:
    if "section_traces" not in st.session_state:
        st.session_state.section_traces = {}
    return st.session_state.section_traces


@dataclass
class TraceStep:
    section: str
    step_id: str
    title: str
    event: dict[str, Any]
    started: float = field(default_factory=time.perf_counter)
    output_summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    status: str = "done"

    def finish(self, output_summary: str = "", detail: dict[str, Any] | None = None, status: str = "done") -> None:
        self.output_summary = output_summary
        self.detail = detail or {}
        self.status = status


@contextmanager
def trace_step(
    section: str,
    step_id: str,
    title: str,
    *,
    tool: str = "",
    model: str = "",
    why: str = "",
    input_summary: str = "",
):
    """记录一个正在执行的步骤；结束后自动写耗时和状态。"""
    event = {
        "id": uuid.uuid4().hex[:8],
        "step_id": step_id,
        "title": title,
        "status": "running",
        "tool": tool,
        "model": model,
        "why": why,
        "input_summary": input_summary,
        "output_summary": "",
        "detail": {},
        "duration_ms": None,
    }
    _store().setdefault(section, []).append(event)
    step = TraceStep(section=section, step_id=step_id, title=title, event=event)
    try:
        yield step
    except Exception as exc:  # noqa: BLE001
        event["status"] = "error"
        event["output_summary"] = f"{type(exc).__name__}: {exc}"
        event["duration_ms"] = int((time.perf_counter() - step.started) * 1000)
        raise
    else:
        event["status"] = step.status
        event["output_summary"] = step.output_summary
        event["detail"] = step.detail
        event["duration_ms"] = int((time.perf_counter() - step.started) * 1000)


def trace_record(
    section: str,
    step_id: str,
    title: str,
    *,
    status: str = "done",
    tool: str = "",
    model: str = "",
    why: str = "",
    input_summary: str = "",
    output_summary: str = "",
    detail: dict[str, Any] | None = None,
    duration_ms: int | None = None,
) -> None:
    _store().setdefault(section, []).append({
        "id": uuid.uuid4().hex[:8],
        "step_id": step_id,
        "title": title,
        "status": status,
        "tool": tool,
        "model": model,
        "why": why,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "detail": detail or {},
        "duration_ms": duration_ms,
    })


def trace_once(section: str, step_id: str, title: str, **kwargs: Any) -> None:
    """静态步骤只保留一条，避免每次 rerun 重复刷屏。"""
    events = _store().setdefault(section, [])
    for e in events:
        if e.get("step_id") == step_id:
            e.update({"title": title, **kwargs})
            return
    trace_record(section, step_id, title, **kwargs)


def _icon(status: str) -> tuple[str, str, str]:
    return STATUS.get(status, ("○", status, "#64748b"))


_CSS = """
<style>
.timeline { border-left: 2px solid #e5e7eb; margin-left: 10px; padding-left: 18px; }
.step { position: relative; margin-bottom: 12px; }
.step .dot { position: absolute; left: -27px; top: 2px; width: 18px; height: 18px;
  border-radius: 50%; background: #fff; border: 3px solid #cbd5e1; font-size: 10px;
  text-align: center; line-height: 14px; color: #475569; }
.step.done .dot { border-color: #16a34a; color: #16a34a; }
.step.running .dot { border-color: #2563eb; color: #2563eb; animation: tpulse 1s infinite; }
.step.error .dot { border-color: #dc2626; color: #dc2626; }
.step.skipped .dot { border-color: #94a3b8; color: #94a3b8; }
.step.waiting_human .dot { border-color: #d97706; color: #d97706; }
@keyframes tpulse { 0% { box-shadow: 0 0 0 0 rgba(37,99,235,.35); } 100% { box-shadow: 0 0 0 8px rgba(37,99,235,0); } }
.step-title { font-weight: 650; font-size: 0.9rem; color: #0f172a; }
.step-meta { color: #64748b; font-size: 0.72rem; margin-top: 1px; }
.step-desc { color: #475569; font-size: 0.78rem; line-height: 1.45; margin-top: 3px; }
.badge { display: inline-block; padding: 0 6px; border-radius: 999px; font-size: 0.68rem;
  margin-left: 5px; background: #f1f5f9; color: #475569; }
.badge.done { background: #dcfce7; color: #166534; }
.badge.running { background: #dbeafe; color: #1d4ed8; }
.badge.error { background: #fee2e2; color: #991b1b; }
.badge.waiting_human { background: #fef3c7; color: #92400e; }
</style>
"""


def render_section_trace(section: str, height: int | None = None) -> None:
    st.markdown("#### 处理记录")
    st.markdown(_CSS, unsafe_allow_html=True)
    events = _store().get(section, [])
    if not events:
        st.caption("暂无记录")
        return

    rows = []
    for e in events[-10:]:
        status = e.get("status", "done")
        sym, label, _ = _icon(status)
        dur = e.get("duration_ms")
        meta = f"用时 {dur / 1000:.1f} 秒" if dur is not None else ""
        rows.append(
            f'<div class="step {status}"><div class="dot">{sym}</div>'
            f'<div class="step-title">{e.get("title", "")}'
            f'<span class="badge {status}">{label}</span></div>'
            f'<div class="step-meta">{meta}</div>'
            f'<div class="step-desc">{e.get("why", "")}</div></div>'
        )
    st.markdown('<div class="timeline">' + "".join(rows) + "</div>", unsafe_allow_html=True)
