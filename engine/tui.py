#!/usr/bin/env python3
"""
tui.py — Terminal interface for Openspired.

Usage:
    python3 engine/tui.py
"""
from __future__ import annotations
import asyncio
import json
import re
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Dependency check ───────────────────────────────────────────────────────────
_MISSING = []
try:
    import yaml
except ImportError:
    _MISSING.append("pyyaml")
try:
    import dotenv
except ImportError:
    _MISSING.append("python-dotenv")

if _MISSING:
    print(f"\n⛔  Missing dependencies: {', '.join(_MISSING)}")
    print(f"   Run: pip3 install {' '.join(_MISSING)}")
    sys.exit(1)

# ── Auto-run setup wizard if workspace isn't configured ───────────────────────
from setup_wizard import needs_setup, run_wizard
if needs_setup():
    run_wizard()

# ── Load config (now that .env is presumably ready) ───────────────────────────
try:
    from config import PROJECT_ROOT, WORKSPACE_DIR, MODEL, JIRA_ENABLED, JIRA_BASE_URL
except EnvironmentError as e:
    print(f"\n⛔  {e}")
    print(f"   Edit .env and add your AI provider key.\n")
    sys.exit(1)

from utils.display import console, _RICH
from utils.logo import print_logo

if _RICH:
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.table import Table
    from rich import box
    from rich.markdown import Markdown
    from rich.rule import Rule


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _clear():
    os.system("clear" if os.name != "nt" else "cls")


def _product_name() -> str:
    try:
        content = (WORKSPACE_DIR / "context" / "global.md").read_text()
        for line in content.split("\n"):
            if line.startswith("# GLOBAL RULES"):
                return line.replace("# GLOBAL RULES —", "").strip()
    except Exception:
        pass
    return "Openspired"


def _sprint_name() -> str:
    try:
        content = (WORKSPACE_DIR / "context" / "sprint_context.md").read_text()
        for line in content.split("\n"):
            if "**Name:**" in line:
                return line.split("**Name:**")[1].strip()
    except Exception:
        pass
    return ""


def _ticket_count() -> int:
    try:
        registry_paths = [
            WORKSPACE_DIR / "logs" / "_Registro.md",
            WORKSPACE_DIR / "logs" / "registry.md",  # fallback legacy
        ]
        for registry in registry_paths:
            if registry.exists():
                rows = [
                    l for l in registry.read_text().split("\n")
                    if re.match(r"^\|\s*(US|DT)-", l.strip())
                ]
                return len(rows)
    except Exception:
        pass
    return 0


def _modules() -> list[str]:
    """List configured modules from workspace/modules/."""
    modules_dir = WORKSPACE_DIR / "modules"
    if not modules_dir.exists():
        return []
    return sorted([d.name for d in modules_dir.iterdir() if d.is_dir()])


def _lang() -> str:
    """Read language preference from workspace (en or es)."""
    try:
        prefs = (WORKSPACE_DIR / "context" / "preferences.md").read_text()
        for line in prefs.split("\n"):
            if line.startswith("language:"):
                return line.split(":")[1].strip().lower()
    except Exception:
        pass
    return "en"


# ─── Ticket template update (from review screen) ──────────────────────────────

_TMPL_LABELS = {
    "en": {
        "title":   "🗂  Ticket Template Editor",
        "current": "Current template",
        "prompt":  (
            "[bold]Rewrite your ticket structure.[/bold]\n\n"
            "[dim]Describe the sections and format your team uses.\n"
            "The Writer agent will follow this template for all future tickets.\n\n"
            "Current template shown above. Describe what you want instead — or paste\n"
            "a blank skeleton with section headers. Press Enter twice when done.[/dim]"
        ),
        "hint":    "Type new template. Press Enter twice when done.",
        "saved":   "✓ Ticket template updated.",
        "cancel":  "Template unchanged.",
    },
    "es": {
        "title":   "🗂  Editor de Plantilla de Ticket",
        "current": "Plantilla actual",
        "prompt":  (
            "[bold]Reescribe la estructura de tus tickets.[/bold]\n\n"
            "[dim]Describe las secciones y el formato que usa tu equipo.\n"
            "El agente Escritor usará esta plantilla para todos los tickets futuros.\n\n"
            "La plantilla actual se muestra arriba. Describe qué quieres cambiar — o\n"
            "pega un esqueleto con encabezados de sección. Presiona Enter dos veces al terminar.[/dim]"
        ),
        "hint":    "Escribe la nueva plantilla. Presiona Enter dos veces al terminar.",
        "saved":   "✓ Plantilla de ticket actualizada.",
        "cancel":  "Plantilla sin cambios.",
    },
}


def _update_ticket_template(lang: str = "en") -> None:
    """Interactive template editor called from the review screen."""
    lb = _TMPL_LABELS.get(lang, _TMPL_LABELS["en"])
    tmpl_path = WORKSPACE_DIR / "context" / "ticket_template.md"

    if not _RICH:
        print("\n=== Ticket Template ===")
        if tmpl_path.exists():
            print(tmpl_path.read_text())
        print("\nPaste your new template (one line at a time). Enter blank line to finish:")
        lines = []
        while True:
            line = input()
            if not line and lines:
                break
            lines.append(line)
        if lines:
            tmpl_path.parent.mkdir(parents=True, exist_ok=True)
            tmpl_path.write_text("\n".join(lines), encoding="utf-8")
            print("Template saved.")
        return

    console.print()
    console.print(Panel(
        f"[bold bright_cyan]{lb['title']}[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(0, 2),
    ))
    console.print()

    if tmpl_path.exists():
        console.print(Panel(
            tmpl_path.read_text(),
            title=f"[dim]{lb['current']}[/dim]",
            border_style="dim",
            padding=(0, 2),
        ))
        console.print()

    console.print(Panel(lb["prompt"], border_style="yellow", padding=(0, 2)))
    console.print()
    console.print(f"  [dim]{lb['hint']}[/dim]")
    console.print()

    new_lines: list[str] = []
    while True:
        line = Prompt.ask("  ▶", default="").strip()
        if not line and new_lines:
            break
        if line:
            new_lines.append(line)

    if new_lines:
        tmpl_path.parent.mkdir(parents=True, exist_ok=True)
        tmpl_path.write_text("\n".join(new_lines), encoding="utf-8")
        console.print(f"\n  [green]{lb['saved']}[/green]")
    else:
        console.print(f"\n  [dim]{lb['cancel']}[/dim]")


def _extract_dependencies(text: str) -> list[str]:
    items = []

    # Formato legacy:
    # [[DEPENDENCIES]]
    # - item 1
    # - item 2
    block_match = re.search(r'\[\[DEPENDENCIES\]\](.*?)(?=\[\[|\Z)', text, re.DOTALL | re.IGNORECASE)
    if block_match:
        block = block_match.group(1).strip()
        for line in block.split('\n'):
            line = line.strip()
            if not line:
                continue
            clean = re.sub(r'^[-*•·]\s+', '', line)
            clean = re.sub(r'^\d+\.\s+', '', clean)
            if clean and not clean.startswith('#'):
                items.append(clean)

    # Formato actual:
    # [[DEPENDENCIES: {"type":"...", "target":"...", "blocking":true, "reason":"..."}]]
    inline = re.findall(r'\[\[DEPENDENCIES:\s*(\{.*?\})\s*\]\]', text, re.DOTALL | re.IGNORECASE)
    for raw_json in inline:
        parsed = None
        try:
            parsed = json.loads(raw_json)
        except Exception:
            parsed = None

        if isinstance(parsed, dict):
            target = str(parsed.get("target", "Dependency")).strip() or "Dependency"
            reason = str(parsed.get("reason", "")).strip()
            blocking = parsed.get("blocking")
            prefix = "[BLOCKING] " if blocking is True else ""
            msg = f"{prefix}{target}"
            if reason:
                msg += f": {reason}"
            items.append(msg)
        else:
            items.append(raw_json.strip())

    return [i for i in items if i]


def _pause():
    if _RICH:
        console.print()
        Prompt.ask("  [dim]↵  back to menu[/dim]", default="")


# ─── Header ───────────────────────────────────────────────────────────────────

def _header():
    name   = _product_name()
    sprint = _sprint_name()
    count  = _ticket_count()
    jira   = "[green]Jira ✓[/green]" if JIRA_ENABLED else "[dim]Jira —[/dim]"

    if _RICH:
        console.print()
        console.print(Panel(
            f"[bold bright_cyan]{name}[/bold bright_cyan]  [dim]powered by Openspired[/dim]\n"
            f"[dim]{MODEL}[/dim]"
            + (f"  ·  [dim]{sprint}[/dim]" if sprint else "")
            + f"  ·  {jira}"
            + (f"  ·  [dim]{count} tickets[/dim]" if count else ""),
            border_style="bright_cyan",
            padding=(0, 2),
        ))
        console.print()
    else:
        print(f"\n{name} — Openspired  |  {MODEL}  |  {sprint}\n")


# ─── Menu ─────────────────────────────────────────────────────────────────────

def _menu():
    is_configured = (WORKSPACE_DIR / "context" / "global.md").exists()
    lang = _lang()

    if _RICH:
        if not is_configured:
            _first_time_msg = (
                "👋  First time here? Start with [bold bright_cyan][0] Setup[/bold bright_cyan] to configure your workspace (~5 min)."
                if lang == "en" else
                "👋  ¿Primera vez? Empieza con [bold bright_cyan][0] Setup[/bold bright_cyan] para configurar tu workspace (~5 min)."
            )
            console.print(Panel(_first_time_msg, border_style="bright_cyan", padding=(0, 2)))
            console.print()

        console.print("  [bold white]CREATE[/bold white]")
        console.print()
        console.print("  [bright_cyan][1][/bright_cyan]  Generate ticket  [dim](guided input)[/dim]")
        console.print("  [bright_cyan][2][/bright_cyan]  Generate from Jira  [dim](read issue → write ticket)[/dim]")
        console.print()
        console.print("  [bold white]REFERENCE[/bold white]")
        console.print()
        console.print("  [bright_cyan][3][/bright_cyan]  View ticket registry")
        console.print("  [bright_cyan][4][/bright_cyan]  View workflows")
        console.print("  [bright_cyan][5][/bright_cyan]  System status")
        console.print()
        console.print("  [bold white]SETTINGS[/bold white]")
        console.print()
        console.print("  [bright_cyan][0][/bright_cyan]  Setup / Re-configure product")
        hist_ok = (WORKSPACE_DIR / "context" / "Contexto_Historico_Proyecto.md").exists()
        hist_label = "[dim](✓ already bootstrapped — re-run to refresh)[/dim]" if hist_ok else "[dim yellow](⚠ not yet run — gives agents historical context)[/dim yellow]"
        console.print(f"  [bright_cyan][6][/bright_cyan]  Bootstrap historical context from Jira  {hist_label}")
        console.print()
        console.print("  [dim][q]  Quit[/dim]")
        console.print()
    else:
        if not is_configured:
            print("\n  First time? Select [0] Setup to get started.\n")
        print("[1] Generate  [2] From Jira  [3] Registry  [4] Workflows  [5] Status  [0] Setup  [6] Bootstrap  [q] Quit")


# ─── [1] Guided input ─────────────────────────────────────────────────────────

def _guided_input() -> str | None:
    if not _RICH:
        return input("Requirement: ").strip() or None

    console.print(Panel(
        "[bold]New Ticket — Request Guide[/bold]\n"
        "[dim]Fill in what you know. Press Enter to skip optional fields.[/dim]",
        border_style="cyan", padding=(0, 2),
    ))
    console.print()

    # Module
    modules = _modules()
    console.print("  [bold cyan]1. Module[/bold cyan]  [dim](which area of your product?)[/dim]")
    if modules:
        console.print(f"     [dim]Configured: {', '.join(modules)}[/dim]")
    module = Prompt.ask("     ▶", default="").strip()
    console.print()

    # Ticket type
    console.print("  [bold cyan]2. Ticket type[/bold cyan]")
    console.print("     [dim][1] User Story   [2] Design Task[/dim]")
    tipo_c = Prompt.ask("     ▶", choices=["1", "2"], default="1")
    tipo = "User Story" if tipo_c == "1" else "Design Task"
    console.print()

    # Requirement
    console.print("  [bold cyan]3. What do you need?[/bold cyan]  [dim](plain language)[/dim]")
    req = Prompt.ask("     ▶", default="").strip()
    console.print()
    if not req:
        console.print("  [red]Requirement cannot be empty.[/red]")
        return None

    # Context
    console.print("  [bold cyan]4. Extra context[/bold cyan]  [dim](Figma link, constraints, dependencies — optional)[/dim]")
    ctx = Prompt.ask("     ▶", default="").strip()
    console.print()

    lines = [
        f"Module: {module}" if module else None,
        f"Type: {tipo}",
        f"Requirement: {req}",
        f"Context: {ctx}" if ctx else None,
    ]
    po_input = "\n".join(l for l in lines if l)

    console.print(Panel(po_input, title="[bold]Summary[/bold]", border_style="dim", padding=(0, 2)))
    console.print()

    if not Confirm.ask("  Run pipeline?", default=True):
        return None

    return po_input


# ─── Human review callback ────────────────────────────────────────────────────

_REVIEW_LABELS = {
    "en": {
        "title":       "🎫 Generated Ticket — Your Review",
        "approve_lbl": "[bold green]Approve[/bold green]",
        "approve_sub": "save ticket + post to Jira",
        "feedback_lbl":"[bold yellow]Feedback[/bold yellow]",
        "feedback_sub":"improve it before saving",
        "template_lbl":"[bold cyan]Update template[/bold cyan]",
        "template_sub":"rewrite your ticket format for future runs",
        "discard_lbl": "Discard",
        "discard_sub": "abandon this ticket",
        "what_rule":   "What would you like to do?",
        "approved":    "✓ Ticket approved — saving...",
        "discarded":   "Ticket discarded.",
        "revising":    "Applying feedback and revising...",
        "feedback_panel": (
            "[bold]What should change?[/bold]\n\n"
            "[dim]Be specific. The Writer agent applies your feedback directly.\n\n"
            "Examples:\n"
            "· 'AC #3 is too vague — specify it must validate X before Y'\n"
            "· 'Add a restriction for BASIC role users in the 2nd AC'\n"
            "· 'Critical flow #2 is wrong — it should start from list view, not the modal'\n"
            "· 'The Spanish translation of the 4th AC is incorrect'[/dim]"
        ),
        "feedback_hint": "Type your feedback. Press Enter twice when done.",
    },
    "es": {
        "title":       "🎫 Ticket Generado — Tu Revisión",
        "approve_lbl": "[bold green]Aprobar[/bold green]",
        "approve_sub": "guardar ticket + enviar a Jira",
        "feedback_lbl":"[bold yellow]Feedback[/bold yellow]",
        "feedback_sub":"mejorar antes de guardar",
        "template_lbl":"[bold cyan]Actualizar plantilla[/bold cyan]",
        "template_sub":"reescribir el formato de ticket para futuras corridas",
        "discard_lbl": "Descartar",
        "discard_sub": "abandonar este ticket",
        "what_rule":   "¿Qué quieres hacer?",
        "approved":    "✓ Ticket aprobado — guardando...",
        "discarded":   "Ticket descartado.",
        "revising":    "Aplicando feedback y revisando...",
        "feedback_panel": (
            "[bold]¿Qué debe cambiar?[/bold]\n\n"
            "[dim]Sé específico. El agente Escritor aplica tu feedback directamente.\n\n"
            "Ejemplos:\n"
            "· 'El AC #3 es muy vago — especifica que debe validar X antes de Y'\n"
            "· 'Agrega una restricción para usuarios de rol BÁSICO en el 2do AC'\n"
            "· 'El flujo crítico #2 está mal — debe comenzar desde la lista, no el modal'\n"
            "· 'La traducción al español del 4to AC es incorrecta'[/dim]"
        ),
        "feedback_hint": "Escribe tu feedback. Presiona Enter dos veces al terminar.",
    },
}


def make_review_callback():
    """
    Returns the human review callback passed to run_pipeline().
    Shows the generated ticket to the PO and captures approval or feedback
    BEFORE the ticket is saved to disk or posted to Jira.

    Return value of the inner function:
        None  → ticket is approved as-is
        str   → feedback text; the Writer agent revises the ticket before saving
    Raises KeyboardInterrupt → ticket is discarded
    """
    lang = _lang()
    lb = _REVIEW_LABELS.get(lang, _REVIEW_LABELS["en"])

    def _review(ticket_text: str, ticket_type: str, module: str, revision: int = 0) -> str | None:
        _clear()
        _header()

        # ── Detect and surface [[DEPENDENCIES]] BEFORE the review menu ────────
        deps = _extract_dependencies(ticket_text)
        if deps and _RICH:
            deps_title = (
                "⚠  This ticket needs your input"
                if lang == "en" else
                "⚠  Este ticket necesita información tuya"
            )
            deps_intro = (
                "[bold yellow]The pipeline flagged these missing items:[/bold yellow]"
                if lang == "en" else
                "[bold yellow]El pipeline marcó estos elementos faltantes:[/bold yellow]"
            )
            deps_note = (
                "[dim]Use [f] Feedback to provide this info and the pipeline will retry.[/dim]"
                if lang == "en" else
                "[dim]Usa [f] Feedback para proporcionar esta info y el pipeline reintentará.[/dim]"
            )
            bullet_list = "\n".join(f"  [yellow]·[/yellow] {d}" for d in deps)
            console.print(Panel(
                f"{deps_intro}\n\n{bullet_list}\n\n{deps_note}",
                title=f"[bold yellow]{deps_title}[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            ))
            console.print()

        if _RICH:
            _rev_badge = (
                f"  [dim]— {'Revision' if lang == 'en' else 'Revisión'} {revision}[/dim]"
                if revision > 0 else ""
            )
            _approve_sub_label = (
                lb['approve_sub']
                if revision == 0
                else ("save + send to Jira" if lang == "en" else "guardar + enviar a Jira")
            )
            console.print(Panel(
                f"[bold]{ticket_type}[/bold]"
                + (f"  ·  [dim]{module}[/dim]" if module else "")
                + _rev_badge,
                title=f"[bold bright_cyan]{lb['title']}[/bold bright_cyan]",
                border_style="bright_cyan" if revision == 0 else "green",
                padding=(0, 2),
            ))
            console.print()

            # Split EN/ES for cleaner display
            if "════" in ticket_text:
                split_marker = next(
                    (l for l in ticket_text.split("\n") if "════" in l and "ESPAÑOL" in l), None
                )
                if split_marker:
                    idx = ticket_text.index(split_marker)
                    en_block = ticket_text[:idx].strip()
                    es_block = ticket_text[idx:].strip()
                    console.print(Panel(en_block, title="[white]English[/white]",
                                        border_style="white", padding=(0, 2)))
                    console.print()
                    console.print(Panel(es_block, title="[dim]Español[/dim]",
                                        border_style="dim", padding=(0, 2)))
                else:
                    console.print(Panel(ticket_text, border_style="white", padding=(0, 2)))
            else:
                console.print(Panel(ticket_text, border_style="white", padding=(0, 2)))

            console.print()
            console.rule(f"[dim]{lb['what_rule']}[/dim]")
            console.print()
            console.print(f"  [bright_cyan][a][/bright_cyan]  {lb['approve_lbl']}    "
                          f"[dim]{_approve_sub_label}[/dim]")
            console.print(f"  [bright_cyan][f][/bright_cyan]  {lb['feedback_lbl']}   "
                          f"[dim]{lb['feedback_sub']}[/dim]")
            console.print(f"  [bright_cyan][t][/bright_cyan]  {lb['template_lbl']}   "
                          f"[dim]{lb['template_sub']}[/dim]")
            console.print(f"  [bright_cyan][d][/bright_cyan]  [dim]{lb['discard_lbl']}    "
                          f"{lb['discard_sub']}[/dim]")
            console.print()

            choice = Prompt.ask(
                "  [bright_cyan]▶[/bright_cyan]",
                choices=["a", "f", "t", "d"],
                default="a",
            ).lower()

            if choice == "a":
                console.print(f"\n  [green]{lb['approved']}[/green]")
                return None

            if choice == "d":
                console.print(f"\n  [yellow]{lb['discarded']}[/yellow]")
                raise KeyboardInterrupt

            if choice == "t":
                _update_ticket_template(lang)
                # After updating template, loop back to the review so PO can still
                # approve / give feedback on this ticket
                return _review(ticket_text, ticket_type, module, revision=revision)

            # Feedback
            console.print()
            console.print(Panel(
                lb["feedback_panel"],
                border_style="yellow",
                padding=(0, 2),
            ))
            console.print()
            console.print(f"  [dim]{lb['feedback_hint']}[/dim]")
            console.print()

            feedback_lines = []
            while True:
                line = Prompt.ask("  ▶", default="").strip()
                if not line and feedback_lines:
                    break
                if line:
                    feedback_lines.append(line)

            feedback = "\n".join(feedback_lines)
            if feedback:
                _iter_note = f" (v{revision + 1})" if revision >= 0 else ""
                console.print(f"\n  [cyan]{lb['revising']}{_iter_note}[/cyan]")
                return feedback

            return None

        else:
            # Plain text fallback
            print("\n" + "─" * 60)
            print(ticket_text)
            print("─" * 60)
            print("\n[a] Approve  [f] Feedback  [t] Update template  [d] Discard")
            choice = input("▶ ").strip().lower()
            if choice == "f":
                print("Your feedback (one line):")
                return input("▶ ").strip() or None
            if choice == "t":
                _update_ticket_template(lang)
                return _review(ticket_text, ticket_type, module, revision=revision)
            if choice == "d":
                raise KeyboardInterrupt
            return None

    return _review


# ─── [2] Jira mode ────────────────────────────────────────────────────────────

def _jira_mode():
    if not JIRA_ENABLED:
        console.print()
        console.print("  [red]Jira is not configured.[/red]")
        console.print("  [dim]Add JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN to .env[/dim]")
        console.print("  [dim]Get your token: https://id.atlassian.com/manage-profile/security/api-tokens[/dim]")
        _pause()
        return

    console.print()
    console.print("  [bold cyan]Jira Issue[/bold cyan]  [dim](e.g. PROJ-123 or full URL)[/dim]")
    issue_ref = Prompt.ask("  ▶", default="").strip()
    if not issue_ref:
        return

    from run import _run_jira_mode
    console.print()
    _errored = False
    try:
        _run_jira_mode(issue_ref, review_callback=make_review_callback())
    except SystemExit as e:
        # sys.exit(0) = user cancelled (KeyboardInterrupt in review) — silent is fine
        # sys.exit(1) = pipeline error — handle_error() already printed the panel,
        #               but we need to make sure the user can read it before _clear()
        if e.code != 0:
            _errored = True
    except KeyboardInterrupt:
        console.print("\n  [dim]Cancelled.[/dim]")
    except Exception as e:
        console.print(f"\n  [red]Unexpected error:[/red] [dim]{e}[/dim]")
        _errored = True

    if _errored:
        console.print()
        console.print("  [yellow]↑ Read the error above before continuing.[/yellow]")
    _pause()


# ─── [3] Ticket registry ──────────────────────────────────────────────────────

def _show_registry():
    path = WORKSPACE_DIR / "logs" / "_Registro.md"
    if not path.exists():
        path = WORKSPACE_DIR / "logs" / "registry.md"  # fallback legacy
    console.print()
    if not path.exists():
        console.print("  [dim]No tickets yet. Create your first one with [1].[/dim]")
        _pause()
        return

    content = path.read_text()
    if not _RICH:
        print(content)
        _pause()
        return

    lines = [l for l in content.split("\n") if l.strip().startswith("|") and "---" not in l]
    if not lines:
        console.print(Panel("[dim]No tickets registered yet.[/dim]", border_style="dim"))
        _pause()
        return

    table = Table(title="Generated Tickets", box=box.ROUNDED, border_style="bright_cyan",
                  show_lines=False, expand=False)
    headers_done = False
    for line in lines:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells:
            continue
        if not headers_done:
            for h in cells:
                table.add_column(h, style="dim" if h.lower() in {"date", "path"} else "bold white")
            headers_done = True
        else:
            first = cells[0] if cells else ""
            row_style = "yellow" if "DT" in first else ("bright_green" if "US" in first else "white")
            table.add_row(*cells, style=row_style)

    console.print(table)
    _pause()


# ─── [4] Workflows ────────────────────────────────────────────────────────────

def _show_workflows():
    wf_dir = PROJECT_ROOT / "agents" / "Workflows"
    console.print()
    workflows = sorted(wf_dir.glob("*.md")) if wf_dir.exists() else []
    if not workflows:
        console.print("  [dim]No workflows found in agents/Workflows/[/dim]")
        _pause()
        return
    for wf_path in workflows:
        preview = "\n".join(wf_path.read_text().split("\n")[:25])
        if _RICH:
            console.print(Panel(Markdown(preview), title=f"[bold]{wf_path.stem}[/bold]",
                                border_style="cyan", padding=(0, 2)))
        else:
            print(f"\n=== {wf_path.stem} ===\n{preview}")
        console.print()
    _pause()


# ─── [5] System status ────────────────────────────────────────────────────────

def _show_status():
    from config import ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, PROVIDER
    key_ok = bool({"anthropic": ANTHROPIC_API_KEY, "google": GOOGLE_API_KEY,
                   "openai": OPENAI_API_KEY}.get(PROVIDER))
    ctx = WORKSPACE_DIR / "context"
    checks = [
        ("AI Provider",       key_ok,                                   f"{PROVIDER.upper()} configured"),
        ("Model",             True,                                     MODEL),
        ("Workspace setup",   (ctx / "global.md").exists(),              "✓"),
        ("Product knowledge", (ctx / "product_knowledge.md").exists(),   "✓"),
        ("Team",              (ctx / "team.md").exists(),                 "✓"),
        ("Reasoning bank",    (ctx / ".reasoning_bank").exists(),         "✓"),
        ("Human feedback",    (ctx / ".reasoning_bank" / "human_feedback.md").exists(), "✓"),
        ("Agents dir",        (PROJECT_ROOT / "agents").exists(),         "✓"),
        ("Modules",           len(_modules()) > 0,                        f"{len(_modules())} configured"),
        ("Jira",              JIRA_ENABLED,
                              f"✓ {JIRA_BASE_URL}" if JIRA_ENABLED else "⚠ Not configured (optional)"),
    ]
    console.print()
    if _RICH:
        table = Table(title="System Status", box=box.ROUNDED, border_style="bright_cyan")
        table.add_column("Component", style="bold white")
        table.add_column("Status")
        table.add_column("Detail", style="dim")
        for name, ok, detail in checks:
            table.add_row(name,
                          "[bright_green]✓  OK[/bright_green]" if ok else "[yellow]⚠  MISSING[/yellow]",
                          detail)
        console.print(table)
    else:
        for name, ok, detail in checks:
            print(f"  {'✓' if ok else '⚠'}  {name}: {detail}")
    _pause()


# ─── [0] Setup ────────────────────────────────────────────────────────────────

def _run_setup():
    run_wizard()


# ─── [6] Bootstrap historical context ─────────────────────────────────────────

def _run_bootstrap():
    from setup_wizard import _bootstrap_historico_from_jira
    from config import JIRA_ENABLED, WORKSPACE_DIR
    lang = _lang()

    console.print()
    if not JIRA_ENABLED:
        console.print(Panel(
            "[yellow]Jira not configured.[/yellow]\n"
            "[dim]Complete JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env\n"
            "or run [0] Setup and connect Jira first.[/dim]",
            border_style="yellow", padding=(0, 2),
        ))
        _pause()
        return

    # Read product name from product_knowledge.md
    pk = WORKSPACE_DIR / "context" / "product_knowledge.md"
    product_name = "Unknown Product"
    if pk.exists():
        for line in pk.read_text().split("\n"):
            if line.startswith("# "):
                product_name = line.lstrip("# ").strip()
                break

    hist_path = WORKSPACE_DIR / "context" / "Contexto_Historico_Proyecto.md"
    action = "Refreshing" if hist_path.exists() else "Generating"
    msg = (f"  [dim]{action} historical context for [bold]{product_name}[/bold] from Jira...[/dim]"
           if lang == "en" else
           f"  [dim]{action} contexto histórico de [bold]{product_name}[/bold] desde Jira...[/dim]")
    console.print(Panel(
        ("[bold]Bootstrap — Historical Context[/bold]\n\n"
         "[dim]Fetches the last 6 months of completed Jira tickets and analyzes them with AI\n"
         "to build a context file that agents use to understand your team's patterns,\n"
         "module structure, and naming conventions. Run this once after connecting Jira.[/dim]"),
        border_style="cyan", padding=(0, 2),
    ))
    console.print()
    console.print(msg)

    ok = _bootstrap_historico_from_jira(lang, product_name)

    console.print()
    if ok:
        console.print(Panel(
            "[green]✓ Historical context bootstrapped successfully.[/green]\n"
            "[dim]Agents will now use your Jira history for better module classification\n"
            "and writing style alignment.[/dim]",
            border_style="green", padding=(0, 2),
        ))
    else:
        console.print(Panel(
            "[yellow]⚠ Bootstrap did not complete.[/yellow]\n"
            "[dim]Check that your API key is valid and Jira credentials are correct.\n"
            "The pipeline still works without historical context.[/dim]",
            border_style="yellow", padding=(0, 2),
        ))
    _pause()


# ─── Pipeline runner ──────────────────────────────────────────────────────────

def _run(po_input: str):
    from pipeline import run_pipeline
    try:
        asyncio.run(run_pipeline(po_input, human_review_callback=make_review_callback()))
    except KeyboardInterrupt:
        console.print("\n  [yellow]Pipeline cancelled.[/yellow]")
    except ValueError as e:
        console.print(f"\n  [yellow]{e}[/yellow]")
    except Exception as e:
        console.print(f"\n  [red]Error: {e}[/red]")
    _pause()


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    ROUTES = {
        "1": lambda: (_clear(), _header(), _run_flow_1()),
        "2": lambda: (_clear(), _header(), _jira_mode()),
        "3": lambda: (_clear(), _header(), _show_registry()),
        "4": lambda: (_clear(), _header(), _show_workflows()),
        "5": lambda: (_clear(), _header(), _show_status()),
        "0": lambda: (_clear(), _run_setup()),
        "6": lambda: (_clear(), _header(), _run_bootstrap()),
    }

    # Show logo once at startup
    _clear()
    print_logo(lang=_lang())

    while True:
        _clear()
        _header()
        _menu()

        choice = (Prompt.ask("  [bright_cyan]▶[/bright_cyan]", default="q")
                  if _RICH else input("▶ ").strip())

        if choice in ("q", "quit", "exit", ""):
            console.print("\n  [dim]Goodbye.[/dim]\n")
            break

        if choice in ROUTES:
            ROUTES[choice]()


def _run_flow_1():
    po_input = _guided_input()
    if po_input:
        console.print()
        _run(po_input)


if __name__ == "__main__":
    main()
