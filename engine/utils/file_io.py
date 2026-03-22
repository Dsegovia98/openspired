"""
utils/file_io.py — Operaciones de lectura/escritura de archivos del proyecto.
"""
from __future__ import annotations
from pathlib import Path
import re
from datetime import datetime, timezone
from config import RUNTIME_PROJECT_ROOT, LOGS_DIR, DOMAIN_PRIMARY


def save_handoff(run_id: str, step: str, content: str) -> Path:
    """Guarda el documento de handoff de un paso del pipeline."""
    run_dir = LOGS_DIR / "pipeline_runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{step}.md"
    path.write_text(content, encoding="utf-8")
    return path


def load_handoff(run_id: str, step: str) -> str:
    """Carga el documento de handoff de un paso anterior."""
    path = LOGS_DIR / "pipeline_runs" / run_id / f"{step}.md"
    if not path.exists():
        raise FileNotFoundError(f"Handoff no encontrado: {path}")
    return path.read_text(encoding="utf-8")


_SEGMENT_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_META_BLOCK_RE = re.compile(r"^\s*<!--\s*OPENSPIRED_META\b.*?-->\s*", re.DOTALL)


def _sanitize_segment(raw: str, fallback: str) -> str:
    """
    Sanitiza un segmento de ruta para evitar traversal y caracteres inválidos.
    Solo permite [A-Za-z0-9._-], colapsa el resto a '-'.
    """
    cleaned = _SEGMENT_SAFE_RE.sub("-", (raw or "").strip())
    cleaned = cleaned.strip(" .-_")
    if not cleaned:
        cleaned = fallback
    if cleaned in {".", ".."}:
        cleaned = f"{fallback}-item"
    return cleaned


def _resolve_within_runtime(path: Path) -> Path:
    """Valida que una ruta final permanezca dentro de RUNTIME_PROJECT_ROOT."""
    root = RUNTIME_PROJECT_ROOT.resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as e:
        raise ValueError(f"Ruta fuera del proyecto runtime no permitida: {path}") from e
    return resolved


def _inject_ticket_meta(
    content: str,
    *,
    ticket_id: str,
    ticket_type: str,
    domain: str,
    scope: str,
    module: str,
    tags: list[str] | None = None,
    run_id: str = "",
) -> str:
    """
    Inyecta metadata legible en el archivo final (US/DT) para trazabilidad.
    Esto asocia explícitamente tags y run al artefacto final.
    """
    cleaned_body = _META_BLOCK_RE.sub("", (content or ""), count=1).lstrip()
    tags_csv = ", ".join([t.strip() for t in (tags or []) if str(t).strip()]) or "-"
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = (
        "<!-- OPENSPIRED_META\n"
        f"artifact: final_ticket\n"
        f"ticket_id: {ticket_id}\n"
        f"ticket_type: {ticket_type}\n"
        f"domain: {domain}\n"
        f"scope: {scope}\n"
        f"module: {module}\n"
        f"run_id: {run_id or '-'}\n"
        f"tags: {tags_csv}\n"
        f"generated_at_utc: {now_iso}\n"
        "-->\n\n"
    )
    return f"{meta}{cleaned_body}" if cleaned_body else meta


def save_final_ticket(ticket_id: str, domain: str, scope: str,
                      module: str, ticket_type: str, content: str,
                      tags: list[str] | None = None, run_id: str = "") -> Path:
    """Guarda el ticket final en la ruta correcta según dominio/scope/módulo.

    Estructura nueva:
      Cake   → Cake/{scope}_Scope/{module}/Design_Tasks/ o USs/
      Analít → Analitica/{disciplina}/{proyecto}/USs/
    """
    safe_ticket_id = _sanitize_segment(ticket_id, "ticket")

    if domain == DOMAIN_PRIMARY:
        type_folder  = "Design_Tasks" if ticket_type == "Design Task" else "USs"
        domain_slug  = _sanitize_segment(DOMAIN_PRIMARY.replace(" ", "_"), "domain")
        scope_slug   = _sanitize_segment(scope, "scope")
        module_slug  = _sanitize_segment(module.replace(" ", "_"), "module")
        path = (RUNTIME_PROJECT_ROOT / domain_slug /
                f"{scope_slug}_Scope" / module_slug / type_folder /
                f"{safe_ticket_id}_{module_slug}.md")
    else:  # Secondary domain (Analytics, Data, etc.)
        disciplina, proyecto = module.split("/", 1) if "/" in module else ("DE", module)
        disciplina_slug = _sanitize_segment(disciplina, "DE")
        proyecto_slug = _sanitize_segment(proyecto, "proyecto")
        path = (RUNTIME_PROJECT_ROOT / "Analitica" / disciplina_slug /
                proyecto_slug / "USs" /
                f"{safe_ticket_id}_{proyecto_slug}.md")

    path = _resolve_within_runtime(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    final_content = _inject_ticket_meta(
        content,
        ticket_id=ticket_id,
        ticket_type=ticket_type,
        domain=domain,
        scope=scope,
        module=module,
        tags=tags,
        run_id=run_id,
    )
    path.write_text(final_content, encoding="utf-8")
    return path


def read_project_file(rel_path: str) -> str:
    """Lee un archivo relativo a la raíz runtime del proyecto."""
    rel = Path(rel_path)
    if rel.is_absolute():
        raise ValueError(f"Ruta absoluta no permitida: {rel_path}")
    full = _resolve_within_runtime(RUNTIME_PROJECT_ROOT / rel)
    return full.read_text(encoding="utf-8") if full.exists() else ""


def write_project_file(rel_path: str, content: str) -> None:
    """Escribe un archivo relativo a la raíz runtime del proyecto."""
    rel = Path(rel_path)
    if rel.is_absolute():
        raise ValueError(f"Ruta absoluta no permitida: {rel_path}")
    full = _resolve_within_runtime(RUNTIME_PROJECT_ROOT / rel)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
