"""
utils/trace_log.py — Genera el Trace Log completo de una ejecución del pipeline.
El Trace Log es el insumo principal para el Meta-Observador.
"""
from __future__ import annotations
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional
from config import PROJECT_ROOT


@dataclass
class AgentStep:
    """Registro de la ejecución de un agente en el pipeline."""
    agent:         str
    input_tokens:  int  = 0
    output_tokens: int  = 0
    duration_secs: float = 0.0
    issues_found:  list[str] = field(default_factory=list)
    summary:       str = ""


@dataclass
class PipelineRun:
    """Estado completo de una ejecución del pipeline."""
    run_id:      str
    ticket_id:   str
    po_input:    str
    domain:      str      = ""
    scope:       str      = ""
    module:      str      = ""
    ticket_type: str      = ""
    ticket_name: str      = ""
    file_path:    str      = ""
    ticket_content: str   = ""
    steps:        list[AgentStep] = field(default_factory=list)
    revisions:   int      = 0
    po_score:    str      = "⚠️ Sin score"
    po_feedback: str      = ""
    escalated:   bool     = False
    started_at:  datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None


def generate_trace_log(run: PipelineRun) -> str:
    """Genera el contenido completo del Trace Log en formato markdown."""
    finished = run.finished_at or datetime.now()
    duration = (finished - run.started_at).total_seconds()

    lines = [
        "---",
        f"Ticket_ID:   {run.ticket_id}",
        f"Run_ID:      {run.run_id}",
        f"Fecha:       {run.started_at.strftime('%Y-%m-%d')}",
        f"Tipo:        {run.ticket_type}",
        f"Dominio:     {run.domain}",
        f"Módulo:      {run.module}",
        f"Duración:    {duration:.0f}s",
        "---",
        "",
        f"# TRACE LOG — {run.ticket_id}: {run.ticket_name}",
        "",
        "## 1. INPUT DEL PO",
        "> Descripción original, sin editar.",
        "",
        run.po_input,
        "",
        "---",
        "",
        "## 2. TRAYECTORIA DE AGENTES",
        "",
    ]

    for step in run.steps:
        issues_str = "\n".join(f"  - {i}" for i in step.issues_found) or "  Ninguno"
        lines += [
            f"### {step.agent}",
            f"**Resumen:** {step.summary}",
            f"**Issues encontrados:**",
            issues_str,
            f"**Duración:** {step.duration_secs:.1f}s",
            "",
        ]

    lines += [
        "---",
        "",
        "## 3. INTERVENCIONES DEL PO",
        "",
        f"**Revisiones internas (anti-loop):** {run.revisions} / 2",
        f"**¿Escaló a [REQUIERE REVISIÓN HUMANA]?:** {'Sí ⚠️' if run.escalated else 'No ✅'}",
        "",
        "| # | Momento | Qué corrigió | Tipo |",
        "|---|---------|-------------|------|",
        "| — | — | *Sin intervenciones registradas* | — |",
        "",
        "---",
        "",
        "## 4. SCORE Y FEEDBACK PO",
        "",
        f"**Score:** {run.po_score}",
        f"**Feedback:** {run.po_feedback or '(Pendiente de feedback del PO)'}",
        "",
        "---",
        "",
        "## 5. EXTRACCIÓN PARA META-OBSERVADOR",
        "",
        "**¿Nuevo patrón exitoso?:** [Meta-Observador completará esto]",
        "**¿Nuevo anti-patrón?:** [Meta-Observador completará esto]",
        "**¿Hechos nuevos para Memory/?:** [Meta-Observador completará esto]",
        "",
        f"**Ruta del ticket:** `{run.file_path}`",
    ]

    return "\n".join(lines)


def save_trace_log(run: PipelineRun) -> None:
    """Guarda el Trace Log en workspace/logs/[ID]_Trace_Log.md"""
    from config import LOGS_DIR
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    path = LOGS_DIR / f"{run.ticket_id}_Trace_Log.md"
    path.write_text(generate_trace_log(run), encoding="utf-8")
