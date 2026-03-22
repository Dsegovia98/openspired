from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

# Ensure config loads safely for tests
_TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="openspired-api-tests-"))
_TEST_WS = _TEST_RUNTIME / "workspace"
(_TEST_WS / "context").mkdir(parents=True, exist_ok=True)
(_TEST_WS / "logs").mkdir(parents=True, exist_ok=True)
(_TEST_WS / "context" / "global.md").write_text("# GLOBAL RULES\n", encoding="utf-8")
(_TEST_RUNTIME / ".env").write_text(
    "PROVIDER=google\nGOOGLE_API_KEY=test-key\nDEFAULT_MODEL=gemini-2.5-flash-lite\n",
    encoding="utf-8",
)

import os
os.environ["WORKSPACE_PATH"] = str(_TEST_WS)
os.environ.pop("PROJECT_PATH", None)

from fastapi.testclient import TestClient

from api_server import create_app
from application.run_manager import RunManager


def _wait_completed(client: TestClient, run_id: str, token: str, timeout: float = 3.0):
    deadline = time.time() + timeout
    headers = {"Authorization": f"Bearer {token}"}
    while time.time() < deadline:
        res = client.get(f"/runs/{run_id}", headers=headers)
        if res.status_code == 200 and res.json().get("status") in {"completed", "failed", "discarded"}:
            return res.json()
        time.sleep(0.02)
    raise AssertionError("Run did not finish in time")


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        def _manual_runner(input_text, _review_cb, event_cb, _opts):
            event_cb({"type": "step_started", "agent": "orquestador"})
            event_cb({"type": "step_completed", "agent": "orquestador"})
            return {"ticket_id": "US-APP-0099", "input": input_text}

        self.manager = RunManager(manual_runner=_manual_runner)
        self.token = "test-token"
        app = create_app(run_manager=self.manager, api_token=self.token, enforce_localhost=False)
        self.client = TestClient(app)
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def test_health_no_auth(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")
        self.assertIn("profile_root", res.json())
        self.assertIn("runtime_project_root", res.json())
        self.assertIn("env_file", res.json())

    def test_setup_allows_bootstrap_without_auth(self):
        res = self.client.post(
            "/setup",
            json={
                "provider": "google",
                "default_model": "gemini-2.5-flash-lite",
                "GOOGLE_API_KEY": "AIza-test",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")
        self.assertEqual(res.json().get("api_token"), self.token)
        self.assertTrue(str(res.json().get("token_path", "")).endswith("/workspace/logs/.api_token"))

        loaded = self.client.get("/setup")
        self.assertEqual(loaded.status_code, 200)
        self.assertIn("env_path", loaded.json())
        self.assertIn("profile_root", loaded.json())
        self.assertIn("workspace_dir", loaded.json())
        self.assertTrue((_TEST_WS / "artifacts" / "ideas").exists())
        self.assertTrue((_TEST_WS / "artifacts" / "dts").exists())
        self.assertTrue((_TEST_WS / "artifacts" / "uss").exists())
        self.assertTrue((_TEST_WS / "links" / "relations.ndjson").exists())

    def test_setup_persists_existing_keys_when_not_reprovided(self):
        first = self.client.post(
            "/setup",
            json={
                "provider": "google",
                "default_model": "gemini-2.5-flash-lite",
                "GOOGLE_API_KEY": "AIza-first",
                "JIRA_API_TOKEN": "jira-first-token",
            },
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/setup",
            json={
                "provider": "google",
                "default_model": "gemini-2.5-flash-lite",
                # no keys this time
            },
        )
        self.assertEqual(second.status_code, 200)

        loaded = self.client.get("/setup")
        self.assertEqual(loaded.status_code, 200)
        data = loaded.json()
        self.assertEqual(data.get("GOOGLE_API_KEY"), "***set***")
        self.assertEqual(data.get("JIRA_API_TOKEN"), "***set***")

    def test_create_run_validation(self):
        res = self.client.post("/runs", json={"mode": "manual"}, headers=self.headers)
        self.assertEqual(res.status_code, 422)

        res2 = self.client.post("/runs", json={"mode": "jira"}, headers=self.headers)
        self.assertEqual(res2.status_code, 422)

    def test_config_status_exposes_profile_contract(self):
        res = self.client.get("/config/status", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertIn("profile", payload)
        self.assertIn("workspace_dir", payload)
        self.assertIn("runtime_project_root", payload)
        self.assertIn("agent_search_dirs", payload)

    def test_create_and_get_run(self):
        res = self.client.post(
            "/runs",
            json={"mode": "manual", "input": "Crear ticket desde API"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        run_id = res.json()["run_id"]

        payload = _wait_completed(self.client, run_id, self.token)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["result"].get("ticket_id"), "US-APP-0099")

    def test_create_run_accepts_tags_in_options(self):
        res = self.client.post(
            "/runs",
            json={
                "mode": "manual",
                "input": "Ticket con tags",
                "options": {"tags": ["release:q1", "priority:high"]},
            },
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("run_id", res.json())

    def test_sse_events_endpoint(self):
        res = self.client.post(
            "/runs",
            json={"mode": "manual", "input": "SSE flow"},
            headers=self.headers,
        )
        run_id = res.json()["run_id"]
        _wait_completed(self.client, run_id, self.token)

        sse = self.client.get(f"/runs/{run_id}/events", headers=self.headers)
        self.assertEqual(sse.status_code, 200)
        self.assertIn("event: message", sse.text)
        self.assertIn("run_completed", sse.text)

    def test_review_conflict_when_not_waiting(self):
        res = self.client.post(
            "/runs",
            json={"mode": "manual", "input": "No review needed"},
            headers=self.headers,
        )
        run_id = res.json()["run_id"]
        _wait_completed(self.client, run_id, self.token)

        conflict = self.client.post(
            f"/runs/{run_id}/review",
            json={"action": "approve"},
            headers=self.headers,
        )
        self.assertEqual(conflict.status_code, 409)

    def test_artifacts_endpoint_contract(self):
        with patch("api_server.list_artifacts", return_value={"items": [], "count": 0, "trace_logs": []}):
            res = self.client.get("/artifacts", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("count", res.json())

    def test_artifacts_reads_registry_and_trace_logs(self):
        registro = _TEST_WS / "logs" / "_Registro.md"
        registro.write_text(
            "# Registro de Tickets — Openspired\n\n"
            "| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| US-APP-0007 | User Story | App | Billing | Título test | — | 2026-03-22 | `App/Global_Scope/Billing/USs/US-APP-0007_Billing.md` |\n",
            encoding="utf-8",
        )
        (_TEST_WS / "logs" / "US-APP-0007_Trace_Log.md").write_text("# trace", encoding="utf-8")

        res = self.client.get("/artifacts", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertGreaterEqual(payload.get("count", 0), 1)
        self.assertTrue(any("US-APP-0007_Trace_Log.md" in p for p in payload.get("trace_logs", [])))

    def test_artifacts_supports_tags_and_grouping(self):
        registro = _TEST_WS / "logs" / "_Registro.md"
        registro.write_text(
            "# Registro de Tickets — Openspired\n\n"
            "| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |\n"
            "|---|---|---|---|---|---|---|---|\n"
            "| US-APP-0010 | User Story | App | Billing | A | — | 2026-03-22 | `a.md` |\n"
            "| DT-APP-0011 | Design Task | App | Billing | B | — | 2026-03-22 | `b.md` |\n",
            encoding="utf-8",
        )
        (_TEST_WS / "logs" / ".artifacts_index.json").write_text(
            "{\n"
            "  \"tickets\": {\n"
            "    \"US-APP-0010\": {\"tags\": [\"release:q1\", \"priority:high\"], \"cost_usd\": 0.0123, \"total_tokens\": 321},\n"
            "    \"DT-APP-0011\": {\"tags\": [\"release:q1\"], \"cost_usd\": 0.0042, \"total_tokens\": 110}\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )

        res = self.client.get("/artifacts?tags=release:q1&group_by=tags", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("count"), 2)
        self.assertIn("grouped_by_tags", payload)
        self.assertIn("release:q1", payload.get("grouped_by_tags", {}))
        first = payload.get("items", [])[0]
        self.assertIn("cost_usd", first)
        self.assertIn("total_tokens", first)
        self.assertIn("tags", first)

    def test_artifacts_reads_tags_from_final_ticket_meta_when_index_missing(self):
        rel_ticket = "App/Global_Scope/Billing/USs/US-APP-0012_Billing.md"
        ticket_file = _TEST_RUNTIME / rel_ticket
        ticket_file.parent.mkdir(parents=True, exist_ok=True)
        ticket_file.write_text(
            "<!-- OPENSPIRED_META\n"
            "ticket_id: US-APP-0012\n"
            "tags: release:q3, priority:medium\n"
            "-->\n\n"
            "# Ticket\n",
            encoding="utf-8",
        )

        registro = _TEST_WS / "logs" / "_Registro.md"
        registro.write_text(
            "# Registro de Tickets — Openspired\n\n"
            "| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |\n"
            "|---|---|---|---|---|---|---|---|\n"
            f"| US-APP-0012 | User Story | App | Billing | Con meta | — | 2026-03-22 | `{rel_ticket}` |\n",
            encoding="utf-8",
        )
        (_TEST_WS / "logs" / ".artifacts_index.json").write_text("{\"tickets\":{}}\n", encoding="utf-8")

        res = self.client.get("/artifacts?tags=release:q3", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("count"), 1)
        self.assertIn("release:q3", payload.get("items", [])[0].get("tags", []))

    def test_artifact_history_endpoint(self):
        (_TEST_WS / "logs" / ".artifacts_index.json").write_text(
            "{\n"
            "  \"tickets\": {\n"
            "    \"US-APP-0099\": {\"run_id\": \"run_demo\", \"tags\": [\"release:q2\"], \"total_tokens\": 777, \"cost_usd\": 0.0301}\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )
        run_dir = _TEST_WS / "logs" / "pipeline_runs" / "run_demo"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "05_ticket_v1.md").write_text("linea uno\nlinea dos\n", encoding="utf-8")
        (run_dir / "05_ticket_human_v1.md").write_text("linea uno\nlinea dos ajustada\n", encoding="utf-8")

        res = self.client.get("/artifacts/US-APP-0099/history", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("ticket_id"), "US-APP-0099")
        self.assertEqual(payload.get("run_id"), "run_demo")
        self.assertEqual(payload.get("count"), 2)
        self.assertIn("release:q2", payload.get("tags", []))

    def test_artifact_history_fallbacks_to_file_meta_when_index_missing(self):
        rel_ticket = "App/Global_Scope/Billing/USs/US-APP-0100_Billing.md"
        ticket_file = _TEST_RUNTIME / rel_ticket
        ticket_file.parent.mkdir(parents=True, exist_ok=True)
        ticket_file.write_text(
            "<!-- OPENSPIRED_META\n"
            "ticket_id: US-APP-0100\n"
            "run_id: run_meta_only\n"
            "tags: release:q4, squad:payments\n"
            "-->\n\n"
            "# Ticket\n",
            encoding="utf-8",
        )
        registro = _TEST_WS / "logs" / "_Registro.md"
        registro.write_text(
            "# Registro de Tickets — Openspired\n\n"
            "| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |\n"
            "|---|---|---|---|---|---|---|---|\n"
            f"| US-APP-0100 | User Story | App | Billing | Meta only | — | 2026-03-22 | `{rel_ticket}` |\n",
            encoding="utf-8",
        )
        (_TEST_WS / "logs" / ".artifacts_index.json").write_text("{\"tickets\":{}}\n", encoding="utf-8")

        run_dir = _TEST_WS / "logs" / "pipeline_runs" / "run_meta_only"
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "05_ticket_v1.md").write_text("alpha\n", encoding="utf-8")
        (run_dir / "05_ticket_human_v1.md").write_text("alpha\nbeta\n", encoding="utf-8")

        res = self.client.get("/artifacts/US-APP-0100/history", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload.get("run_id"), "run_meta_only")
        self.assertIn("release:q4", payload.get("tags", []))
        self.assertEqual(payload.get("count"), 2)


if __name__ == "__main__":
    unittest.main()
