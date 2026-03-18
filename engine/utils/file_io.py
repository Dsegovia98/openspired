"""
utils/file_io.py — Operaciones de lectura/escritura de archivos del proyecto.
"""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
from config import PROJECT_ROOT, LOGS_DIR, DOMAIN_PRIMARY


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


def save_final_ticket(ticket_id: str, domain: str, scope: str,
                      module: str, ticket_type: str, content: str) -> Path:
    """Guarda el ticket final en la ruta correcta según dominio/scope/módulo.

    Estructura nueva:
      Cake   → Cake/{scope}_Scope/{module}/Design_Tasks/ o USs/
      Analít → Analitica/{disciplina}/{proyecto}/USs/
    """
    if domain == DOMAIN_PRIMARY:
        type_folder  = "Design_Tasks" if ticket_type == "Design Task" else "USs"
        domain_slug  = DOMAIN_PRIMARY.replace(" ", "_")
        path = (PROJECT_ROOT / domain_slug /
                f"{scope}_Scope" / module / type_folder /
                f"{ticket_id}_{module.replace(' ', '_')}.md")
    else:  # Secondary domain (Analytics, Data, etc.)
        disciplina, proyecto = module.split("/", 1) if "/" in module else ("DE", module)
        path = (PROJECT_ROOT / "Analitica" / disciplina.strip() /
                proyecto.strip() / "USs" /
                f"{ticket_id}_{proyecto.strip().replace(' ', '_')}.md")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def read_project_file(rel_path: str) -> str:
    """Lee un archivo relativo a PROJECT_ROOT."""
    full = PROJECT_ROOT / rel_path
    return full.read_text(encoding="utf-8") if full.exists() else ""


def write_project_file(rel_path: str, content: str) -> None:
    """Escribe un archivo relativo a PROJECT_ROOT."""
    full = PROJECT_ROOT / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
