from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

RunMode = Literal["manual", "jira"]
RunStatus = Literal[
    "queued",
    "running",
    "waiting_human",
    "completed",
    "failed",
    "discarded",
]
ReviewActionType = Literal["approve", "feedback", "discard"]


@dataclass(slots=True)
class ReviewAction:
    action: ReviewActionType
    feedback: str = ""


@dataclass(slots=True)
class RunRequest:
    mode: RunMode
    input_text: str = ""
    jira_issue_key: str = ""
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunEvent:
    id: int
    run_id: str
    type: str
    payload: dict[str, Any]
    timestamp: str


@dataclass(slots=True)
class RunRecord:
    run_id: str
    request: RunRequest
    status: RunStatus = "queued"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    events_count: int = 0
