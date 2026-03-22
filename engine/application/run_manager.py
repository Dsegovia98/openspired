from __future__ import annotations

import asyncio
import queue
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from pipeline import run_pipeline

from .jira_service import run_pipeline_from_jira
from .models import ReviewAction, RunEvent, RunRecord, RunRequest


class RunNotFoundError(KeyError):
    pass


class InvalidRunStateError(RuntimeError):
    pass


class _RunState:
    def __init__(self, record: RunRecord):
        self.record = record
        self.events: list[RunEvent] = []
        self.condition = threading.Condition()
        self.review_queue: "queue.Queue[ReviewAction]" = queue.Queue()


class RunManager:
    """
    Serial run orchestrator for local API/Desktop usage.

    - One active run at a time.
    - Supports human review gate via /review endpoint.
    - Stores event stream in memory for SSE consumption.
    """

    def __init__(
        self,
        manual_runner: Callable[..., Any] | None = None,
        jira_runner: Callable[..., Any] | None = None,
    ):
        self._manual_runner = manual_runner or self._default_manual_runner
        self._jira_runner = jira_runner or self._default_jira_runner

        self._runs: dict[str, _RunState] = {}
        self._lock = threading.Lock()
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, name="openspired-run-worker", daemon=True)
        self._worker.start()

    # ── Public API ──────────────────────────────────────────────────────────

    def submit_run(self, request: RunRequest) -> str:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        record = RunRecord(run_id=run_id, request=request)
        state = _RunState(record)

        with self._lock:
            self._runs[run_id] = state

        self._append_event(run_id, "run_queued", {"mode": request.mode})
        self._queue.put(run_id)
        return run_id

    def get_run(self, run_id: str) -> RunRecord:
        state = self._get_state(run_id)
        rec = state.record
        return RunRecord(
            run_id=rec.run_id,
            request=rec.request,
            status=rec.status,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
            result=dict(rec.result),
            error=rec.error,
            events_count=len(state.events),
        )

    def list_runs(self, limit: int = 50) -> list[RunRecord]:
        with self._lock:
            runs = list(self._runs.values())
        runs.sort(key=lambda s: s.record.created_at, reverse=True)
        return [self.get_run(s.record.run_id) for s in runs[:max(1, limit)]]

    def submit_review(self, run_id: str, action: ReviewAction) -> None:
        state = self._get_state(run_id)
        if state.record.status != "waiting_human":
            raise InvalidRunStateError(
                f"Run {run_id} no está esperando revisión humana (status actual: {state.record.status})"
            )
        state.review_queue.put(action)

    def wait_for_event(self, run_id: str, after_id: int = 0, timeout_secs: float = 20.0) -> tuple[int, dict[str, Any]] | None:
        state = self._get_state(run_id)
        deadline = time.monotonic() + max(0.1, timeout_secs)

        with state.condition:
            while len(state.events) <= after_id:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                state.condition.wait(timeout=remaining)

            next_event = state.events[after_id]
            return next_event.id, self._event_to_dict(next_event)

    # ── Worker internals ────────────────────────────────────────────────────

    def _worker_loop(self) -> None:
        while True:
            run_id = self._queue.get()
            try:
                self._execute_run(run_id)
            finally:
                self._queue.task_done()

    def _execute_run(self, run_id: str) -> None:
        state = self._get_state(run_id)
        request = state.record.request

        self._set_status(run_id, "running")
        self._append_event(run_id, "run_started", {"mode": request.mode})

        try:
            review_callback = self._build_review_callback(run_id)
            pipeline_event_callback = lambda e: self._append_event(run_id, e.get("type", "pipeline_event"), e)

            if request.mode == "manual":
                result = self._manual_runner(
                    request.input_text,
                    review_callback,
                    pipeline_event_callback,
                    request.options,
                )
            elif request.mode == "jira":
                result = self._jira_runner(
                    request.jira_issue_key,
                    review_callback,
                    pipeline_event_callback,
                    request.options,
                )
            else:
                raise ValueError(f"Modo no soportado: {request.mode}")

            result_payload = self._serialize_result(result)
            state.record.result = result_payload
            self._set_status(run_id, "completed")
            self._append_event(run_id, "run_completed", result_payload)

        except KeyboardInterrupt:
            self._set_status(run_id, "discarded")
            self._append_event(run_id, "run_discarded", {})
        except Exception as e:
            state.record.error = str(e)
            self._set_status(run_id, "failed")
            self._append_event(run_id, "run_failed", {"error": str(e), "error_type": type(e).__name__})

    def _build_review_callback(self, run_id: str):
        def _callback(ticket_text: str, ticket_type: str, module: str, revision: int = 0) -> str | None:
            self._set_status(run_id, "waiting_human")
            self._append_event(run_id, "review_required", {
                "ticket_text": ticket_text,
                "ticket_type": ticket_type,
                "module": module,
                "revision": revision,
            })

            state = self._get_state(run_id)
            action = state.review_queue.get()

            if action.action == "approve":
                self._set_status(run_id, "running")
                self._append_event(run_id, "review_approved", {"revision": revision})
                return None

            if action.action == "feedback":
                self._set_status(run_id, "running")
                self._append_event(run_id, "review_feedback", {
                    "revision": revision,
                    "feedback": action.feedback,
                })
                return action.feedback

            if action.action == "discard":
                self._append_event(run_id, "review_discarded", {"revision": revision})
                raise KeyboardInterrupt

            self._append_event(run_id, "review_invalid_action", {"action": action.action})
            return None

        return _callback

    # ── Default runners ─────────────────────────────────────────────────────

    @staticmethod
    def _default_manual_runner(
        input_text: str,
        review_callback: Callable[..., str | None] | None,
        event_callback: Callable[[dict[str, Any]], None] | None,
        options: dict[str, Any] | None = None,
    ):
        opts = options or {}
        return asyncio.run(
            run_pipeline(
                input_text,
                human_review_callback=review_callback,
                event_callback=event_callback,
                ticket_tags=list(opts.get("tags", []) or []),
            )
        )

    @staticmethod
    def _default_jira_runner(
        jira_issue_key: str,
        review_callback: Callable[..., str | None] | None,
        event_callback: Callable[[dict[str, Any]], None] | None,
        options: dict[str, Any] | None = None,
    ):
        return asyncio.run(
            run_pipeline_from_jira(
                jira_issue_key,
                review_callback=review_callback,
                event_callback=event_callback,
                options=options or {},
            )
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _get_state(self, run_id: str) -> _RunState:
        with self._lock:
            state = self._runs.get(run_id)
        if not state:
            raise RunNotFoundError(run_id)
        return state

    def _set_status(self, run_id: str, status: str) -> None:
        state = self._get_state(run_id)
        state.record.status = status  # type: ignore[assignment]
        state.record.updated_at = datetime.now(timezone.utc)

    def _append_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
        state = self._get_state(run_id)
        with state.condition:
            event_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            event = RunEvent(
                id=len(state.events) + 1,
                run_id=run_id,
                type=event_type,
                payload=payload,
                timestamp=event_ts,
            )
            state.events.append(event)
            state.record.updated_at = datetime.now(timezone.utc)
            state.record.events_count = len(state.events)
            state.condition.notify_all()

    @staticmethod
    def _event_to_dict(event: RunEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "run_id": event.run_id,
            "type": event.type,
            "timestamp": event.timestamp,
            "payload": event.payload,
        }

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        if hasattr(result, "__dataclass_fields__"):
            data = asdict(result)
            # JSON-safe coercion for datetime values
            for key, val in list(data.items()):
                if isinstance(val, datetime):
                    data[key] = val.isoformat().replace("+00:00", "Z")
            return data
        if isinstance(result, dict):
            return dict(result)
        return {"result": str(result)}
