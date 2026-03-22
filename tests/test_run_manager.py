from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from application.models import ReviewAction, RunRequest
from application.run_manager import RunManager


def _wait_status(manager: RunManager, run_id: str, expected: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = manager.get_run(run_id).status
        if status == expected:
            return
        time.sleep(0.02)
    raise AssertionError(f"Run {run_id} did not reach status '{expected}' in time")


class RunManagerTests(unittest.TestCase):
    def test_manual_run_completes_and_emits_events(self):
        def _manual_runner(input_text, _review_cb, event_cb, _opts):
            event_cb({"type": "step_started", "agent": "orquestador"})
            event_cb({"type": "step_completed", "agent": "orquestador"})
            return {"ticket_id": "US-APP-0001", "input": input_text}

        manager = RunManager(manual_runner=_manual_runner)
        run_id = manager.submit_run(RunRequest(mode="manual", input_text="Crear login"))

        _wait_status(manager, run_id, "completed")
        record = manager.get_run(run_id)

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.result.get("ticket_id"), "US-APP-0001")
        self.assertGreaterEqual(record.events_count, 3)  # queued + started + completed

    def test_review_flow_feedback_then_approve(self):
        def _manual_runner(_input_text, review_cb, _event_cb, _opts):
            feedback = review_cb("v1", "User Story", "Billing", revision=0)
            if feedback:
                review_cb("v2", "User Story", "Billing", revision=1)
            return {"ticket_id": "US-APP-0002", "feedback": feedback}

        manager = RunManager(manual_runner=_manual_runner)
        run_id = manager.submit_run(RunRequest(mode="manual", input_text="US con revisión"))

        _wait_status(manager, run_id, "waiting_human")
        manager.submit_review(run_id, ReviewAction(action="feedback", feedback="Ajusta AC 2"))

        _wait_status(manager, run_id, "waiting_human")
        manager.submit_review(run_id, ReviewAction(action="approve"))

        _wait_status(manager, run_id, "completed")
        record = manager.get_run(run_id)
        self.assertEqual(record.result.get("feedback"), "Ajusta AC 2")

    def test_discard_flow(self):
        def _manual_runner(_input_text, review_cb, _event_cb, _opts):
            review_cb("v1", "User Story", "Support", revision=0)
            return {"ticket_id": "US-APP-0003"}

        manager = RunManager(manual_runner=_manual_runner)
        run_id = manager.submit_run(RunRequest(mode="manual", input_text="Descartar"))

        _wait_status(manager, run_id, "waiting_human")
        manager.submit_review(run_id, ReviewAction(action="discard"))
        _wait_status(manager, run_id, "discarded")


if __name__ == "__main__":
    unittest.main()
