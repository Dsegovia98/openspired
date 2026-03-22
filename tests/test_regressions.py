from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))


_TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="openspired-tests-"))
_TEST_WORKSPACE = _TEST_RUNTIME / "workspace"
(_TEST_WORKSPACE / "context").mkdir(parents=True, exist_ok=True)
(_TEST_WORKSPACE / "logs").mkdir(parents=True, exist_ok=True)
(_TEST_WORKSPACE / "context" / "global.md").write_text("# GLOBAL RULES — TEST\n", encoding="utf-8")
(_TEST_WORKSPACE / "context" / "preferences.md").write_text("language: en\n", encoding="utf-8")
(_TEST_RUNTIME / ".env").write_text(
    "PROVIDER=google\n"
    "GOOGLE_API_KEY=test-google-key\n"
    "DEFAULT_MODEL=gemini-2.5-flash-lite\n",
    encoding="utf-8",
)
os.environ["WORKSPACE_PATH"] = str(_TEST_WORKSPACE)
os.environ.pop("PROJECT_PATH", None)


import config  # noqa: E402
import map_interface  # noqa: E402
import setup_wizard  # noqa: E402
import tui  # noqa: E402
from utils import file_io, registro  # noqa: E402


class _FakeHTTPResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FilePathSecurityTests(unittest.TestCase):
    def test_save_final_ticket_keeps_path_inside_runtime(self):
        with tempfile.TemporaryDirectory(prefix="openspired-root-") as td:
            root = Path(td)
            with patch.object(file_io, "RUNTIME_PROJECT_ROOT", root), patch.object(file_io, "DOMAIN_PRIMARY", "App"):
                path = file_io.save_final_ticket(
                    ticket_id="US-APP-0001",
                    domain="App",
                    scope="Global",
                    module="../../../../etc",
                    ticket_type="User Story",
                    content="ticket body",
                )
                self.assertTrue(path.exists())
                self.assertTrue(path.resolve().is_relative_to(root.resolve()))
                self.assertNotIn("..", str(path))

    def test_save_final_ticket_embeds_meta_with_tags(self):
        with tempfile.TemporaryDirectory(prefix="openspired-root-") as td:
            root = Path(td)
            with patch.object(file_io, "RUNTIME_PROJECT_ROOT", root), patch.object(file_io, "DOMAIN_PRIMARY", "App"):
                path = file_io.save_final_ticket(
                    ticket_id="US-APP-0002",
                    domain="App",
                    scope="Global",
                    module="Billing",
                    ticket_type="User Story",
                    content="# Ticket\n\nBody",
                    tags=["release:q2", "priority:high"],
                    run_id="run_abc123",
                )
                text = path.read_text(encoding="utf-8")
                self.assertIn("<!-- OPENSPIRED_META", text)
                self.assertIn("ticket_id: US-APP-0002", text)
                self.assertIn("tags: release:q2, priority:high", text)
                self.assertIn("# Ticket", text)

    def test_write_project_file_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory(prefix="openspired-root-") as td:
            root = Path(td)
            with patch.object(file_io, "RUNTIME_PROJECT_ROOT", root):
                with self.assertRaises(ValueError):
                    file_io.write_project_file("../escape.md", "nope")
                with self.assertRaises(ValueError):
                    file_io.read_project_file("/tmp/absolute.md")


class TicketIdConcurrencyTests(unittest.TestCase):
    def test_allocate_ticket_id_is_unique_in_parallel(self):
        with tempfile.TemporaryDirectory(prefix="openspired-registry-") as td:
            work_logs = Path(td) / "logs"
            work_logs.mkdir(parents=True, exist_ok=True)
            reg_path = work_logs / "_Registro.md"
            counters_path = work_logs / ".ticket_counters.json"

            with patch.object(registro, "REGISTRO_PATH", reg_path), patch.object(registro, "COUNTERS_PATH", counters_path):
                def _reserve(_):
                    return registro.allocate_ticket_id("User Story", "App")

                with ThreadPoolExecutor(max_workers=10) as executor:
                    ids = list(executor.map(_reserve, range(40)))

                self.assertEqual(len(ids), len(set(ids)))
                nums = sorted(int(tid.split("-")[-1]) for tid in ids)
                self.assertEqual(nums, list(range(1, 41)))


class TuiRegressionTests(unittest.TestCase):
    def test_ticket_count_reads_registro_file(self):
        with tempfile.TemporaryDirectory(prefix="openspired-tui-") as td:
            ws = Path(td) / "workspace"
            logs = ws / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "_Registro.md").write_text(
                "| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |\n"
                "|---|---|---|---|---|---|---|---|\n"
                "| US-APP-0001 | User Story | App | Billing | A | — | 2026-01-01 | `a.md` |\n"
                "| DT-APP-0002 | Design Task | App | Billing | B | — | 2026-01-01 | `b.md` |\n",
                encoding="utf-8",
            )
            with patch.object(tui, "WORKSPACE_DIR", ws):
                self.assertEqual(tui._ticket_count(), 2)

    def test_extract_dependencies_supports_json_marker(self):
        text = (
            "Texto previo\n"
            '[[DEPENDENCIES: {"type":"api","target":"Billing API","blocking":true,"reason":"Missing endpoint"}]]\n'
            '[[DEPENDENCIES: {"type":"context","target":"UX copy","blocking":false,"reason":"Pending wording"}]]\n'
        )
        deps = tui._extract_dependencies(text)
        self.assertTrue(any("Billing API" in d and "[BLOCKING]" in d for d in deps))
        self.assertTrue(any("UX copy" in d for d in deps))


class MapInterfaceRegressionTests(unittest.TestCase):
    def test_google_vision_branch_uses_current_config_fields(self):
        captured = {}

        def _fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            return _FakeHTTPResponse(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "map ok"}]}}
                    ]
                }
            )

        with patch.object(config, "PROVIDER", "google"), patch.object(config, "DEFAULT_MODEL", "gemini-2.5-flash-lite"), patch.object(config, "GOOGLE_API_KEY", "k"), patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            out = map_interface._analyze_screenshot_with_vision("ZmFrZQ==", "https://example.com", "")
        self.assertEqual(out, "map ok")
        self.assertIn("gemini-2.5-flash-lite", captured["url"])


class SetupWizardOpenAITests(unittest.TestCase):
    def test_bootstrap_historico_openai_works_with_http_path(self):
        with tempfile.TemporaryDirectory(prefix="openspired-wizard-") as td:
            root = Path(td)
            ws = root / "workspace"
            (ws / "context").mkdir(parents=True, exist_ok=True)
            (root / ".env").write_text(
                "PROVIDER=openai\n"
                "DEFAULT_MODEL=gpt-4o-mini\n"
                "OPENAI_API_KEY=sk-valid-test-key-1234567890\n"
                "JIRA_BASE_URL=https://example.atlassian.net\n"
                "JIRA_EMAIL=test@example.com\n"
                "JIRA_API_TOKEN=test-token\n"
                "JIRA_PROJECT_KEY=APP\n",
                encoding="utf-8",
            )

            calls = {"count": 0}

            def _fake_urlopen(req, timeout=0):
                calls["count"] += 1
                if "search/jql" in req.full_url:
                    return _FakeHTTPResponse(
                        {
                            "issues": [
                                {
                                    "key": "APP-1",
                                    "fields": {
                                        "issuetype": {"name": "Story"},
                                        "assignee": {"displayName": "Ana"},
                                        "status": {"name": "Done"},
                                        "summary": "Implement checkout step",
                                    },
                                }
                            ]
                        }
                    )
                if "api.openai.com" in req.full_url:
                    return _FakeHTTPResponse(
                        {"choices": [{"message": {"content": "## Team & Roles\n- Ana"}}]}
                    )
                raise AssertionError(f"Unexpected URL in test: {req.full_url}")

            with patch.object(setup_wizard, "PROJECT_ROOT", root), patch.object(setup_wizard, "PROFILE_ROOT", root), patch.object(setup_wizard, "WORKSPACE_DIR", ws), patch("urllib.request.urlopen", side_effect=_fake_urlopen):
                ok = setup_wizard._bootstrap_historico_from_jira("es", "Producto Test")

            self.assertTrue(ok)
            out_file = ws / "context" / "Contexto_Historico_Proyecto.md"
            self.assertTrue(out_file.exists())
            self.assertIn("Ana", out_file.read_text(encoding="utf-8"))
            self.assertGreaterEqual(calls["count"], 2)


if __name__ == "__main__":
    unittest.main()
