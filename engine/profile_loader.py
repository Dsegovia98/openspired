from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


PROFILE_SCHEMA_VERSION = 1
DEFAULT_MIN_ENGINE_VERSION = "1.0.0"
DEFAULT_RELATIONS_FILE = "links/relations.ndjson"


def _workspace_layout_dirs() -> tuple[str, ...]:
    """
    Canonical profile workspace layout (tenant-safe and project-agnostic).

    Includes legacy folders for backward compatibility with current pipeline.
    """
    return (
        "context/.reasoning_bank",
        "context/modules",
        "context/artifacts",
        "context/tickets",
        "artifacts",
        "artifacts/ideas",
        "artifacts/research",
        "artifacts/prds",
        "artifacts/dts",
        "artifacts/uss",
        "links",
        "logs/pipeline_runs",
        # Legacy paths kept intentionally.
        "modules",
        "tickets",
    )


def ensure_workspace_layout(workspace_dir: Path) -> None:
    workspace_dir = workspace_dir.resolve()
    for rel in _workspace_layout_dirs():
        (workspace_dir / rel).mkdir(parents=True, exist_ok=True)

    relations = workspace_dir / DEFAULT_RELATIONS_FILE
    if not relations.exists():
        relations.write_text("", encoding="utf-8")


@dataclass(frozen=True)
class RuntimePaths:
    core_project_root: Path
    profile_root: Path
    runtime_project_root: Path
    workspace_dir: Path
    env_file: Path
    profile_file: Path | None
    profile_name: str
    profile_schema_version: int | None
    profile_min_engine: str | None
    source: str
    agents_dir: Path
    agents_override_dir: Path | None
    agent_search_dirs: tuple[Path, ...]


def _clean_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _resolve_path(base: Path, value: Any, fallback: Path) -> Path:
    raw = _clean_value(value)
    if not raw:
        return fallback
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


def _load_profile_toml(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}

    with path.open("rb") as handle:
        parsed = tomllib.load(handle)
    return parsed if isinstance(parsed, dict) else {}


def _profile_path_value(profile_data: dict[str, Any], key: str) -> Any:
    paths = profile_data.get("paths", {})
    if isinstance(paths, dict) and key in paths:
        return paths.get(key)

    alt_keys = {
        "workspace": ["workspace", "workspace_path", "WORKSPACE_PATH"],
        "agents": ["agents", "agents_path", "AGENTS_PATH"],
        "project": ["project", "project_path", "PROJECT_PATH"],
        "env": ["env", "env_path", "ENV_PATH"],
    }.get(key, [key])

    for k in alt_keys:
        if k in profile_data:
            return profile_data.get(k)
    return None


def resolve_runtime_paths(
    core_project_root: Path,
    environ: Mapping[str, str] | None = None,
) -> RuntimePaths:
    env = dict(os.environ) if environ is None else dict(environ)
    core_project_root = core_project_root.resolve()
    core_agents_dir = (core_project_root / "agents").resolve()

    profile_env = _clean_value(env.get("OPENSPIRED_PROFILE_PATH") or env.get("PROFILE_PATH"))
    project_env = _clean_value(env.get("PROJECT_PATH"))
    workspace_env = _clean_value(env.get("WORKSPACE_PATH"))
    agents_env = _clean_value(env.get("AGENTS_PATH"))

    if profile_env:
        source = "profile_env"
        profile_root = Path(profile_env).expanduser().resolve()
    elif project_env:
        source = "project_env"
        profile_root = Path(project_env).expanduser().resolve()
    elif workspace_env:
        source = "workspace_env"
        profile_root = Path(workspace_env).expanduser().resolve().parent
    else:
        source = "core_default"
        profile_root = core_project_root

    profile_file = (profile_root / "profile.toml").resolve()
    profile_data = _load_profile_toml(profile_file)

    runtime_project_root = _resolve_path(
        profile_root,
        project_env or _profile_path_value(profile_data, "project"),
        profile_root,
    )
    workspace_dir = _resolve_path(
        profile_root,
        workspace_env or _profile_path_value(profile_data, "workspace"),
        runtime_project_root / "workspace",
    )
    env_file = _resolve_path(
        profile_root,
        env.get("OPENSPIRED_ENV_PATH") or _profile_path_value(profile_data, "env"),
        profile_root / ".env",
    )

    # Only treat agents dir as external overrides when a profile/env explicitly exists.
    has_explicit_profile = bool(profile_env or project_env or workspace_env or profile_data)
    default_agents_override = runtime_project_root / "agents" if has_explicit_profile else core_agents_dir

    agents_dir = _resolve_path(
        profile_root,
        agents_env or _profile_path_value(profile_data, "agents"),
        default_agents_override,
    )

    profile_meta = profile_data.get("profile", {}) if isinstance(profile_data.get("profile"), dict) else {}
    profile_name = _clean_value(profile_meta.get("name")) or profile_root.name
    profile_schema_raw = profile_meta.get("schema_version")
    try:
        profile_schema_version = int(profile_schema_raw) if profile_schema_raw is not None else None
    except (TypeError, ValueError):
        profile_schema_version = None
    profile_min_engine = _clean_value(
        profile_meta.get("min_engine_version") or profile_meta.get("min_engine")
    ) or None

    agents_override_dir: Path | None
    if agents_dir.resolve() != core_agents_dir.resolve():
        agents_override_dir = agents_dir
    elif has_explicit_profile and agents_env:
        agents_override_dir = agents_dir
    else:
        agents_override_dir = None

    search_dirs: list[Path] = []
    if agents_override_dir is not None:
        search_dirs.append(agents_override_dir)
    if not any(p.resolve() == core_agents_dir for p in search_dirs):
        search_dirs.append(core_agents_dir)

    # Keep backward-compatible single AGENTS_DIR value as the highest-priority dir.
    primary_agents = search_dirs[0] if search_dirs else core_agents_dir

    return RuntimePaths(
        core_project_root=core_project_root,
        profile_root=profile_root,
        runtime_project_root=runtime_project_root,
        workspace_dir=workspace_dir,
        env_file=env_file,
        profile_file=profile_file if profile_file.exists() else None,
        profile_name=profile_name,
        profile_schema_version=profile_schema_version,
        profile_min_engine=profile_min_engine,
        source=source,
        agents_dir=primary_agents,
        agents_override_dir=agents_override_dir,
        agent_search_dirs=tuple(search_dirs),
    )


def resolve_agent_file(relative_path: str | Path, search_dirs: tuple[Path, ...]) -> Path:
    rel = Path(relative_path)
    for base in search_dirs:
        candidate = base / rel
        if candidate.exists() and candidate.is_file():
            return candidate
    return search_dirs[0] / rel


def _write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def bootstrap_profile(
    profile_root: Path,
    *,
    name: str,
    workspace_rel: str = "workspace",
    agents_rel: str = "agents",
    min_engine_version: str = DEFAULT_MIN_ENGINE_VERSION,
) -> dict[str, str]:
    profile_root = profile_root.expanduser().resolve()
    workspace_dir = (profile_root / workspace_rel).resolve()
    agents_dir = (profile_root / agents_rel).resolve()

    ensure_workspace_layout(workspace_dir)
    agents_dir.mkdir(parents=True, exist_ok=True)

    profile_toml = profile_root / "profile.toml"
    if not profile_toml.exists():
        profile_toml.write_text(
            "\n".join(
                [
                    "[profile]",
                    f'name = "{name}"',
                    f"schema_version = {PROFILE_SCHEMA_VERSION}",
                    f'min_engine_version = "{min_engine_version}"',
                    "",
                    "[paths]",
                    f'workspace = "{workspace_rel}"',
                    f'agents = "{agents_rel}"',
                    "",
                ]
            ),
            encoding="utf-8",
        )

    # Optional placeholders to make first run less fragile.
    _write_if_missing(
        agents_dir / "README.md",
        "# Agent Overrides\n\nPlace only profile-specific overrides here. Core agents stay in OpenSpired.\n",
    )

    return {
        "profile_root": str(profile_root),
        "workspace_dir": str(workspace_dir),
        "agents_dir": str(agents_dir),
        "profile_toml": str(profile_toml),
    }
