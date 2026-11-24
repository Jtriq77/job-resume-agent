"""Agent 事件模型：所有步骤通过事件流暴露给前端。

设计原则：
- 前端不写死进度，所有状态来自后端 emit 的真实事件；
- 每个事件都带 why / tool / input / output / duration / confidence；
- trace 可落盘、可回放，报告和演示共用同一份记录。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


class Status:
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"
    WAITING_HUMAN = "waiting_human"


@dataclass
class AgentEvent:
    run_id: str
    seq: int
    step_id: str
    title: str
    status: str
    why: str = ""
    tool: str = ""
    model: str = ""
    input_summary: str = ""
    output_summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    confidence: float | None = None
    retry_count: int = 0
    human_gate: bool = False
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EventBus:
    """收集事件，并可选地回调给前端。"""

    def __init__(self, run_id: str | None = None, on_event: Callable[[AgentEvent], None] | None = None):
        self.run_id = run_id or new_run_id()
        self.events: list[AgentEvent] = []
        self.on_event = on_event
        self._seq = 0

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def emit(self, event: AgentEvent) -> AgentEvent:
        self.events.append(event)
        if self.on_event:
            self.on_event(event)
        return event

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": self.run_id,
            "saved_at": now_iso(),
            "events": [e.to_dict() for e in self.events],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    @staticmethod
    def load(path: str | Path) -> dict[str, Any]:
        return json.loads(Path(path).read_text(encoding="utf-8"))
