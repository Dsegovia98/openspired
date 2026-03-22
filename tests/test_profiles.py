from __future__ import annotations

import tempfile
import unittest
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = REPO_ROOT / "engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from profile_loader import (
    PROFILE_SCHEMA_VERSION,
    bootstrap_profile,
    resolve_agent_file,
    resolve_runtime_paths,
)


class ProfileResolutionTests(unittest.TestCase):
    def test_default_mode_uses_core_paths(self):
        with tempfile.TemporaryDirectory(prefix="openspired-core-") as td:
            core = Path(td)
            (core / "agents").mkdir(parents=True, exist_ok=True)
            core_r = core.resolve()

            resolved = resolve_runtime_paths(core, environ={})

            self.assertEqual(resolved.profile_root, core_r)
            self.assertEqual(resolved.runtime_project_root, core_r)
            self.assertEqual(resolved.workspace_dir, (core / "workspace").resolve())
            self.assertEqual(resolved.agents_dir, (core / "agents").resolve())
            self.assertEqual(resolved.agent_search_dirs, ((core / "agents").resolve(),))
            self.assertIsNone(resolved.profile_file)

    def test_profile_toml_is_respected(self):
        with tempfile.TemporaryDirectory(prefix="openspired-core-") as core_td, tempfile.TemporaryDirectory(prefix="openspired-profile-") as profile_td:
            core = Path(core_td)
            profile = Path(profile_td)
            (core / "agents").mkdir(parents=True, exist_ok=True)
            core_agents = (core / "agents").resolve()
            profile_r = profile.resolve()

            (profile / "profile.toml").write_text(
                "\n".join(
                    [
                        "[profile]",
                        'name = "Blossom"',
                        f"schema_version = {PROFILE_SCHEMA_VERSION}",
                        'min_engine_version = "1.0.0"',
                        "",
                        "[paths]",
                        'workspace = "workspace_data"',
                        'agents = "agent_overrides"',
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            env = {"OPENSPIRED_PROFILE_PATH": str(profile)}
            resolved = resolve_runtime_paths(core, environ=env)

            self.assertEqual(resolved.profile_name, "Blossom")
            self.assertEqual(resolved.profile_root, profile_r)
            self.assertEqual(resolved.workspace_dir, (profile / "workspace_data").resolve())
            self.assertEqual(resolved.agents_dir, (profile / "agent_overrides").resolve())
            self.assertEqual(resolved.env_file, (profile / ".env").resolve())
            self.assertEqual(resolved.agent_search_dirs[0], (profile / "agent_overrides").resolve())
            self.assertEqual(resolved.agent_search_dirs[1], core_agents)

    def test_env_paths_override_profile_toml_paths(self):
        with tempfile.TemporaryDirectory(prefix="openspired-core-") as core_td, tempfile.TemporaryDirectory(prefix="openspired-profile-") as profile_td, tempfile.TemporaryDirectory(prefix="openspired-custom-") as custom_td:
            core = Path(core_td)
            profile = Path(profile_td)
            custom = Path(custom_td)
            (core / "agents").mkdir(parents=True, exist_ok=True)

            (profile / "profile.toml").write_text(
                "[paths]\nworkspace = \"workspace_a\"\nagents = \"agents_a\"\n",
                encoding="utf-8",
            )

            env = {
                "OPENSPIRED_PROFILE_PATH": str(profile),
                "WORKSPACE_PATH": str(custom / "workspace_b"),
                "AGENTS_PATH": str(custom / "agents_b"),
                "PROJECT_PATH": str(custom / "project_b"),
            }
            resolved = resolve_runtime_paths(core, environ=env)

            self.assertEqual(resolved.runtime_project_root, (custom / "project_b").resolve())
            self.assertEqual(resolved.workspace_dir, (custom / "workspace_b").resolve())
            self.assertEqual(resolved.agents_dir, (custom / "agents_b").resolve())

    def test_agent_resolution_prefers_profile_override(self):
        with tempfile.TemporaryDirectory(prefix="openspired-core-") as core_td, tempfile.TemporaryDirectory(prefix="openspired-profile-") as profile_td:
            core = Path(core_td)
            profile = Path(profile_td)
            core_agents = core / "agents"
            profile_agents = profile / "agents"
            core_agents.mkdir(parents=True, exist_ok=True)
            profile_agents.mkdir(parents=True, exist_ok=True)

            rel = Path("00_Orquestador") / "00_Orquestador.md"
            (core_agents / rel).parent.mkdir(parents=True, exist_ok=True)
            (profile_agents / rel).parent.mkdir(parents=True, exist_ok=True)
            (core_agents / rel).write_text("core", encoding="utf-8")
            (profile_agents / rel).write_text("override", encoding="utf-8")

            picked = resolve_agent_file(rel, (profile_agents, core_agents))
            self.assertEqual(picked, profile_agents / rel)


class ProfileBootstrapTests(unittest.TestCase):
    def test_bootstrap_profile_creates_contract_structure(self):
        with tempfile.TemporaryDirectory(prefix="openspired-profile-") as td:
            root = Path(td)

            result = bootstrap_profile(root, name="Blossom")

            self.assertTrue((root / "profile.toml").exists())
            self.assertTrue((root / "workspace" / "context" / ".reasoning_bank").exists())
            self.assertTrue((root / "workspace" / "context" / "modules").exists())
            self.assertTrue((root / "workspace" / "context" / "artifacts").exists())
            self.assertTrue((root / "workspace" / "context" / "tickets").exists())
            self.assertTrue((root / "workspace" / "artifacts" / "ideas").exists())
            self.assertTrue((root / "workspace" / "artifacts" / "research").exists())
            self.assertTrue((root / "workspace" / "artifacts" / "prds").exists())
            self.assertTrue((root / "workspace" / "artifacts" / "dts").exists())
            self.assertTrue((root / "workspace" / "artifacts" / "uss").exists())
            self.assertTrue((root / "workspace" / "links").exists())
            self.assertTrue((root / "workspace" / "links" / "relations.ndjson").exists())
            self.assertTrue((root / "workspace" / "logs" / "pipeline_runs").exists())
            self.assertTrue((root / "workspace" / "modules").exists())
            self.assertTrue((root / "workspace" / "tickets").exists())
            self.assertTrue((root / "agents" / "README.md").exists())
            self.assertEqual(result["profile_root"], str(root.resolve()))


if __name__ == "__main__":
    unittest.main()
