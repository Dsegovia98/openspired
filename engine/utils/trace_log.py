"""
utils/trace_log.py — Genera el Trace Log completo de una ejecución del pipeline.
El Trace Log es el insumo principal para el Meta-Observador.
"""
from __future__ import annotations
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional


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
    tags:         list[str] = field(default_factory=list)
    file_path:    str      = ""
    ticket_content: str   = ""
    steps:        list[AgentStep] = field(default_factory=list)
    revisions:   int      = 0
    po_score:    str      = "⚠️ Sin score"
    po_feedback: str      = ""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    escalated:   bool     = False
    started_at:  datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None


def generate_trace_log(run: PipelineRun) -> str:
    """Genera el contenido completo del Trace Log en formato markdown."""
    finished = run.finished_at or datetime.now()
    duration = (finished - run.started_at).total_seconds()

    # Construir tabla de intervenciones del PO
    if run.po_feedback.strip():
        po_rows = [
            f"| {i+1} | {line.strip()} |"
            for i, line in enumerate(run.po_feedback.strip().splitlines())
            if line.strip()
        ]
    else:
        po_rows = ["| — | *Sin intervenciones del PO* |"]

    lines = [
        "---",
        f"Ticket_ID:   {run.ticket_id}",
        f"Run_ID:      {run.run_id}",
        f"Fecha:       {run.started_at.strftime('%Y-%m-%d')}",
        f"Tipo:        {run.ticket_type}",
        f"Dominio:     {run.domain}",
        f"Módulo:      {run.module}",
        f"Tags:        {', '.join(run.tags) if run.tags else '-'}",
        f"Duracion:    {duration:.0f}s",
        "---",
        "",
        f"# TRACE LOG — {run.ticket_id}: {run.ticket_name}",
        "",
        "## 1. INPUT DEL PO",
        "> Descripcion original, sin editar.",
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
        token_summary = f"{step.input_tokens}/{step.output_tokens}" if (step.input_tokens or step.output_tokens) else "-"
        lines += [
            f"### {step.agent}",
            f"**Resumen:** {step.summary}",
            f"**Issues encontrados:**",
            issues_str,
            f"**Tokens (input/output):** {token_summary}",
            f"**Duracion:** {step.duration_secs:.1f}s",
            "",
        ]

    lines += [
        "---",
        "",
        "## 2.1 COSTO Y TOKENS",
        "",
        f"**Tokens totales (input/output):** {run.total_input_tokens} / {run.total_output_tokens}",
        f"**Costo estimado total (USD):** {run.total_cost_usd:.6f}",
        "",
        "## 3. INTERVENCIONES DEL PO",
        "",
        f"**Revisiones internas (anti-loop):** {run.revisions} / 2",
        f"**Escalo a [REQUIERE REVISION HUMANA]:** {'Si' if run.escalated else 'No'}",
        "",
        "| # | Feedback del PO |",
        "|---|----------------|",
        *po_rows,
        "",
        "---",
        "",
        "## 4. SCORE Y FEEDBACK PO",
        "",
        f"**Score:** {run.po_score}",
        f"**Feedback:** {run.po_feedback or '(Sin feedback del PO)'}",
        "",
        "---",
        "",
        "## 5. EXTRACCION PARA META-OBSERVADOR",
        "",
        "**Nuevo patron exitoso:** [Meta-Observador completara esto]",
        "**Nuevo anti-patron:** [Meta-Observador completara esto]",
        "**Hechos nuevos para Memory/:** [Meta-Observador completara esto]",
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
