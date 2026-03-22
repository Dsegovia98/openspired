from __future__ import annotations

import config


def get_config_status() -> dict:
    key_ok = bool(
        {
            "anthropic": config.ANTHROPIC_API_KEY,
            "google": config.GOOGLE_API_KEY,
            "openai": config.OPENAI_API_KEY,
        }.get(config.PROVIDER)
    )

    return {
        "provider": config.PROVIDER,
        "model": config.MODEL,
        "api_key_configured": key_ok,
        "profile": {
            "name": config.PROFILE_NAME,
            "root": str(config.PROFILE_ROOT),
            "file": str(config.PROFILE_FILE) if config.PROFILE_FILE else "",
            "source": config.PROFILE_SOURCE,
            "schema_version": config.PROFILE_SCHEMA_VERSION,
            "min_engine_version": config.PROFILE_MIN_ENGINE or "",
        },
        "workspace_dir": str(config.WORKSPACE_DIR),
        "runtime_project_root": str(config.RUNTIME_PROJECT_ROOT),
        "env_file": str(config.ENV_FILE),
        "require_profile": config.REQUIRE_PROFILE,
        "core_env_ignored": config.CORE_ENV_IGNORED,
        "env_migrated_from_core": config.ENV_MIGRATED_FROM_CORE,
        "logs_dir": str(config.LOGS_DIR),
        "agents_dir": str(config.AGENTS_DIR),
        "agent_search_dirs": [str(p) for p in config.AGENT_SEARCH_DIRS],
        "jira_enabled": config.JIRA_ENABLED,
        "checks": {
            "global_context": (config.WORKSPACE_DIR / "context" / "global.md").exists(),
            "reasoning_bank": (config.WORKSPACE_DIR / "context" / ".reasoning_bank").exists(),
            "registro": (config.WORKSPACE_DIR / "logs" / "_Registro.md").exists(),
        },
    }
