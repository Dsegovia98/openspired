"""
utils/display.py — UI de terminal con ANSI nativo (fallback si rich no está).
Funciona sin dependencias externas.
"""
from __future__ import annotations
import sys
import threading
import time

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
    from rich.table import Table
    from rich import box
    _RICH = True
except ImportError:
    _RICH = False

# ─── ANSI colors ──────────────────────────────────────────────────────────────
_C = {
    "cyan":    "\033[96m",  "blue":   "\033[94m",  "magenta": "\033[95m",
    "yellow":  "\033[93m",  "green":  "\033[92m",  "red":     "\033[91m",
    "white":   "\033[97m",  "dim":    "\033[2m",   "bold":    "\033[1m",
    "reset":   "\033[0m",
}
AGENT_ANSI = {
    "orquestador": _C["cyan"],   "ideador": _C["magenta"],
    "researcher":  _C["blue"],   "dev_concepto": _C["yellow"],
    "escritor":    _C["green"],  "qa": _C["red"],
    "feedback":    _C["yellow"], "documentador": _C["cyan"],
    "meta_observador": _C["magenta"],
}

console = Console() if _RICH else None

# Paleta de colores por agente
AGENT_COLORS = {
    "orquestador":   "bright_cyan",
    "ideador":       "bright_magenta",
    "researcher":    "bright_blue",
    "dev_concepto":  "bright_yellow",
    "escritor":      "bright_green",
    "qa":            "bright_red",
    "feedback":      "orange3",
    "documentador":  "steel_blue1",
    "meta_observador": "medium_purple",
}

AGENT_ICONS = {
    "orquestador":    "🎯",
    "ideador":        "💡",
    "researcher":     "🔍",
    "dev_concepto":   "🏗️",
    "escritor":       "✍️",
    "qa":             "🧪",
    "feedback":       "⚡",
    "documentador":   "📁",
    "meta_observador":"🧠",
}


def print_banner(po_input: str) -> None:
    """Muestra el banner inicial del pipeline."""
    if _RICH:
        console.print()
        console.print(Panel(
            f"[bold white]{po_input}[/bold white]",
            title="[bold bright_cyan]🌸 PRODUCT AGENTS — PIPELINE INICIADO[/bold bright_cyan]",
            border_style="bright_cyan",
            padding=(1, 2),
        ))
        console.print()
    else:
        print("\n" + "="*60)
        print("🌸 PRODUCT AGENTS — PIPELINE INICIADO")
        print("="*60)
        print(po_input)
        print("="*60 + "\n")


def print_step_start(step_num: int, agent_name: str, description: str = "") -> None:
    """Anuncia el inicio de un paso del pipeline."""
    icon  = AGENT_ICONS.get(agent_name, "▶")
    color = AGENT_COLORS.get(agent_name, "white")
    label = agent_name.replace("_", " ").title()

    if _RICH:
        console.print(
            f"  [{color}]{icon} Paso {step_num} — [bold]{label}[/bold][/{color}]"
            + (f" [dim]{description}[/dim]" if description else "")
        )
    else:
        print(f"\n{icon} Paso {step_num} — {label}{' — ' + description if description else ''}")


def print_step_done(agent_name: str, duration: float) -> None:
    """Confirma la finalización de un paso."""
    color = AGENT_COLORS.get(agent_name, "white")
    if _RICH:
        console.print(f"  [{color}]  ✓ Completado en {duration:.1f}s[/{color}]")
    else:
        print(f"  ✓ Completado en {duration:.1f}s")


def print_parallel_start(agents: list[str]) -> None:
    """Anuncia ejecución paralela."""
    labels = " + ".join(a.replace("_", " ").title() for a in agents)
    if _RICH:
        console.print(f"\n  [dim]⟳ Ejecutando en paralelo:[/dim] [bold]{labels}[/bold]")
    else:
        print(f"\n  ⟳ Paralelo: {labels}")


def print_revision(revision_num: int, issues: list[str]) -> None:
    """Anuncia una revisión del anti-loop."""
    if _RICH:
        console.print(f"\n  [yellow]⚠ Revisión {revision_num}/2 — {len(issues)} issue(s) detectado(s)[/yellow]")
        for issue in issues[:3]:
            console.print(f"    [dim]· {issue[:80]}[/dim]")
    else:
        print(f"\n  ⚠ Revisión {revision_num}/2 — {len(issues)} issue(s)")


def print_escalation(ticket_id: str) -> None:
    """Anuncia escalamiento al PO."""
    if _RICH:
        console.print(Panel(
            f"[bold]Ticket {ticket_id}[/bold] requiere revisión manual del PO.\n"
            "Se agotaron las 2 iteraciones automáticas de revisión.",
            title="[bold red]🚨 REQUIERE REVISIÓN HUMANA[/bold red]",
            border_style="red",
        ))
    else:
        print(f"\n🚨 ESCALAMIENTO: {ticket_id} requiere revisión humana.\n")


def print_success(ticket_id: str, ticket_name: str, file_path: str, duration: float) -> None:
    """Muestra el resumen final exitoso."""
    if _RICH:
        console.print()
        console.print(Panel(
            f"[bold bright_green]{ticket_id}[/bold bright_green]  [white]{ticket_name}[/white]\n\n"
            f"[dim]Guardado en:[/dim] [cyan]{file_path}[/cyan]\n"
            f"[dim]Tiempo total:[/dim] {duration:.0f}s",
            title="[bold bright_green]✅ TICKET GENERADO[/bold bright_green]",
            border_style="bright_green",
            padding=(1, 2),
        ))
        console.print()
    else:
        print(f"\n✅ TICKET GENERADO: {ticket_id}")
        print(f"   {ticket_name}")
        print(f"   Guardado en: {file_path}")
        print(f"   Tiempo total: {duration:.0f}s\n")


def make_progress() -> "Progress":
    """Crea un contexto de progreso rich (o un dummy si rich no está disponible)."""
    if _RICH:
        return Progress(
            SpinnerColumn(style="bright_cyan"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30, style="bright_cyan"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )
    # Dummy context manager si rich no está disponible
    class _Dummy:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def add_task(self, *a, **kw): return 0
        def advance(self, *a, **kw): pass
    return _Dummy()
