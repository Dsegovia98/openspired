"""
application/project_service.py — Read/write project context files from the profile workspace.

These files live in ~/Library/Application Support/com.openspired.desktop/runtime/workspace/context/
and are never committed to the open-source repo.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config

# ── File manifest ─────────────────────────────────────────────────────────────
# Defines which context files are exposed through the API, with metadata.

@dataclass(frozen=True)
class ContextFileMeta:
    key: str           # stable identifier used in API paths
    label: str         # display name
    description: str   # one-liner for UI tooltip
    filename: str      # actual filename in workspace/context/
    editable: bool = True
    subdir: str = ""   # subdirectory inside context/ (e.g. ".reasoning_bank")


CONTEXT_FILES: list[ContextFileMeta] = [
    ContextFileMeta(
        key="product_knowledge",
        label="Conocimiento del Producto",
        description="Qué hace el producto, módulos principales, integraciones. Lo leen todos los agentes.",
        filename="product_knowledge.md",
    ),
    ContextFileMeta(
        key="global",
        label="Reglas Globales",
        description="Plataforma, roles, convenciones de formato. Se aplica en cada corrida del pipeline.",
        filename="global.md",
    ),
    ContextFileMeta(
        key="sprint_context",
        label="Contexto de Sprint",
        description="Sprint actual, épicas activas, objetivos del sprint. Actualizar al inicio de cada sprint.",
        filename="sprint_context.md",
    ),
    ContextFileMeta(
        key="team",
        label="Equipo",
        description="Directorio de personas y roles. Usado para asignación automática de tickets.",
        filename="team.md",
    ),
    ContextFileMeta(
        key="ticket_template",
        label="Plantilla de Tickets",
        description="Estructura base que usa el Escritor. Puede importarse automáticamente desde Jira.",
        filename="ticket_template.md",
    ),
    ContextFileMeta(
        key="historical_context",
        label="Contexto Histórico",
        description="Módulos, épicas y patrones extraídos del historial de Jira. Generado por el bootstrap.",
        filename="Contexto_Historico_Proyecto.md",
    ),
    ContextFileMeta(
        key="successful_patterns",
        label="Patrones Exitosos",
        description="Estilo de escritura y estructuras aprobadas. Lo lee el Escritor antes de generar cada ticket.",
        filename="patrones_exitosos.md",
        subdir=".reasoning_bank",
    ),
    ContextFileMeta(
        key="human_feedback",
        label="Feedback Humano",
        description="Historial de feedback dado en revisiones. El Escritor aprende de estos datos.",
        filename="human_feedback.md",
        subdir=".reasoning_bank",
        editable=False,
    ),
]

_KEY_MAP: dict[str, ContextFileMeta] = {f.key: f for f in CONTEXT_FILES}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _file_path(meta: ContextFileMeta) -> Path:
    base = config.WORKSPACE_DIR / "context"
    if meta.subdir:
        return base / meta.subdir / meta.filename
    return base / meta.filename


# ── Public API ────────────────────────────────────────────────────────────────

def list_context_files() -> list[dict[str, Any]]:
    """Return metadata + existence status for all context files."""
    results = []
    for meta in CONTEXT_FILES:
        path = _file_path(meta)
        results.append({
            "key": meta.key,
            "label": meta.label,
            "description": meta.description,
            "filename": meta.filename,
            "editable": meta.editable,
            "exists": path.exists(),
            "size": path.stat().st_size if path.exists() else 0,
        })
    return results


def get_context_file(key: str) -> dict[str, Any]:
    """Return content of a specific context file."""
    meta = _KEY_MAP.get(key)
    if not meta:
        raise KeyError(f"Unknown context file key: {key!r}")

    path = _file_path(meta)
    if not path.exists():
        return {
            "key": key,
            "label": meta.label,
            "content": "",
            "exists": False,
        }

    return {
        "key": key,
        "label": meta.label,
        "content": path.read_text(encoding="utf-8"),
        "exists": True,
        "editable": meta.editable,
    }


def save_context_file(key: str, content: str) -> dict[str, Any]:
    """Overwrite a context file. Raises if not editable or key unknown."""
    meta = _KEY_MAP.get(key)
    if not meta:
        raise KeyError(f"Unknown context file key: {key!r}")
    if not meta.editable:
        raise PermissionError(f"File {key!r} is read-only (auto-managed by agents).")

    path = _file_path(meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    return {
        "key": key,
        "label": meta.label,
        "size": path.stat().st_size,
        "status": "saved",
    }
