from __future__ import annotations

from pathlib import Path
from typing import Any

import config
from profile_loader import bootstrap_profile, ensure_workspace_layout


def _set_env_line(env_text: str, key: str, value: str) -> str:
    lines = env_text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return "\n".join(lines)
    lines.append(f"{key}={value}")
    return "\n".join(lines)


def _ensure_context_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _path_for_profile(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(config.PROFILE_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def apply_setup(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Applies a structured setup payload for desktop/API onboarding.

    This intentionally performs a safe baseline setup (directories, env values,
    and minimal context files) without invoking interactive prompts.
    """
    env_path = config.ENV_FILE
    current = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    provider = str(payload.get("provider", "google")).strip().lower() or "google"
    default_model = str(payload.get("default_model", config.DEFAULT_MODEL)).strip() or config.DEFAULT_MODEL
    language = str(payload.get("language", "en")).strip().lower() or "en"
    profile_name = str(payload.get("profile_name", config.PROFILE_NAME)).strip() or config.PROFILE_NAME

    current = _set_env_line(current, "PROVIDER", provider)
    current = _set_env_line(current, "DEFAULT_MODEL", default_model)

    # API keys (keep existing value if payload omits)
    for key in ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"]:
        if key in payload and str(payload.get(key, "")).strip():
            current = _set_env_line(current, key, str(payload[key]).strip())

    # Jira optional config
    for key in [
        "JIRA_BASE_URL",
        "JIRA_EMAIL",
        "JIRA_API_TOKEN",
        "JIRA_PROJECT_KEY",
        "JIRA_PROJECT_KEY_SECONDARY",
        "DOMAIN_PRIMARY",
        "DOMAIN_SECONDARY",
    ]:
        if key in payload:
            value = str(payload.get(key, "")).strip()
            # Preserve existing values when payload sends empty defaults.
            if value:
                current = _set_env_line(current, key, value)

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(current.strip() + "\n", encoding="utf-8")

    profile_info: dict[str, str] = {}
    if config.PROFILE_ROOT.resolve() != config.PROJECT_ROOT.resolve():
        profile_info = bootstrap_profile(
            config.PROFILE_ROOT,
            name=profile_name,
            workspace_rel=_path_for_profile(config.WORKSPACE_DIR),
            agents_rel=_path_for_profile(config.AGENTS_DIR),
        )

    # Ensure canonical workspace runtime layout.
    ensure_workspace_layout(config.WORKSPACE_DIR)

    # Minimal context stubs for first run
    _ensure_context_file(
        config.WORKSPACE_DIR / "context" / "global.md",
        "# GLOBAL RULES — Product\n\n- Keep tickets clear and testable.\n",
    )
    _ensure_context_file(
        config.WORKSPACE_DIR / "context" / "product_knowledge.md",
        "# PRODUCT KNOWLEDGE\n\n## What is this product?\n(TBD)\n",
    )
    _ensure_context_file(
        config.WORKSPACE_DIR / "context" / "sprint_context.md",
        "# SPRINT CONTEXT\n\n- Sprint: Sprint 1\n",
    )
    _ensure_context_file(
        config.WORKSPACE_DIR / "context" / "team.md",
        "# TEAM\n\n| Name | Role |\n|---|---|\n",
    )
    _ensure_context_file(
        config.WORKSPACE_DIR / "context" / "ticket_template.md",
        "# TICKET TEMPLATE\n\nAs a [Role]\nI want [Action]\nSo that [Value]\n",
    )

    (config.WORKSPACE_DIR / "context" / "preferences.md").write_text(
        f"language: {language}\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "provider": provider,
        "default_model": default_model,
        "profile_name": profile_name,
        "profile_root": str(config.PROFILE_ROOT),
        "workspace": str(config.WORKSPACE_DIR),
        "env_path": str(env_path),
        "profile": profile_info,
    }
