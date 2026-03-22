#!/usr/bin/env python3
"""
run.py — Punto de entrada del pipeline Product Agents.

Uso:
    python run.py                              # Modo interactivo
    python run.py "Agregar X al módulo Y"      # Input directo
    python run.py --check                      # Verificar configuración
    python run.py --jira CAKE-123              # Input desde Jira, output a Jira
    python run.py --jira https://tu.atlassian.net/browse/CAKE-123
"""
from __future__ import annotations
import sys
import os
import asyncio
import argparse
import textwrap

# ─── Verificación de dependencias críticas antes de importar nada más ─────────
# anthropic y rich son opcionales — el sistema usa urllib nativo y ANSI puro.
# Solo yaml y dotenv son requeridos (ya incluidos en el entorno base).
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
    print("\n⛔  Dependencias faltantes:", ", ".join(_MISSING))
    print("   pip install", " ".join(_MISSING), "\n")
    sys.exit(1)

# Bootstrap: permitir iniciar la API local sin API key previa para habilitar setup UI.
if "--serve-api" in sys.argv:
    os.environ.setdefault("OPENSPIRED_ALLOW_EMPTY_CONFIG", "true")

# ─── Imports del sistema ──────────────────────────────────────────────────────
try:
    from config import (
        ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, PROVIDER, MODEL,
        PROJECT_ROOT, RUNTIME_PROJECT_ROOT, WORKSPACE_DIR, LOGS_DIR, AGENTS_DIR,
        PROFILE_NAME, PROFILE_ROOT, PROFILE_SOURCE,
        JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_ENABLED,
    )
except EnvironmentError as e:
    print(f"\n⛔  {e}\n")
    sys.exit(1)

from utils.display import console, _RICH, _C
from pipeline import run_pipeline, run_meta_on_rejection

if _RICH:
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich import box


# ─── Funciones de UI ──────────────────────────────────────────────────────────

def print_header() -> None:
    if _RICH:
        console.print()
        console.print(Panel(
            "[bold bright_cyan]Openspired[/bold bright_cyan]  "
            "[dim]Sistema Multi-Agente — Pipeline de Generación de Tickets[/dim]\n\n"
            f"[dim]Modelo:[/dim] [cyan]{MODEL}[/cyan]   "
            f"[dim]Proyecto:[/dim] [cyan]{RUNTIME_PROJECT_ROOT.name}[/cyan]   "
            f"[dim]Profile:[/dim] [cyan]{PROFILE_NAME}[/cyan]",
            border_style="bright_cyan",
            padding=(0, 2),
        ))
        console.print()
    else:
        print("\n Openspired — Pipeline Multi-Agente")
        print(f"   Modelo: {MODEL} | Proyecto: {RUNTIME_PROJECT_ROOT.name} | Profile: {PROFILE_NAME}\n")


def print_check() -> None:
    """Muestra el estado de la configuración del sistema."""
    _key_ok = bool({"anthropic": ANTHROPIC_API_KEY, "google": GOOGLE_API_KEY, "openai": OPENAI_API_KEY}.get(PROVIDER))
    checks = [
        ("API Key",         _key_ok, f"Configurada ({PROVIDER})" if _key_ok else f"FALTA {PROVIDER.upper()}_API_KEY"),
        ("Modelo",          True,    MODEL),
        ("_Registro.md",    (WORKSPACE_DIR / "logs/_Registro.md").exists(),  str(WORKSPACE_DIR / "logs/_Registro.md")),
        ("Context/global",  (WORKSPACE_DIR / "context/global.md").exists(), "✓"),
        ("ReasoningBank",   (WORKSPACE_DIR / "context/.reasoning_bank").exists(), "✓"),
        ("Logs dir",        LOGS_DIR.exists(), "✓"),
        ("Agents dir",      AGENTS_DIR.exists(), str(AGENTS_DIR)),
        ("Profile",         True, f"{PROFILE_NAME} ({PROFILE_SOURCE})"),
        ("Profile root",    PROFILE_ROOT.exists(), str(PROFILE_ROOT)),
        ("Jira",            True, "✓ Configurada" if JIRA_ENABLED else "⚠ No configurada (opcional)"),
    ]

    if _RICH:
        table = Table(title="Estado del Sistema", box=box.ROUNDED, border_style="bright_cyan")
        table.add_column("Componente", style="bold white")
        table.add_column("Estado")
        table.add_column("Detalle", style="dim")

        for name, ok, detail in checks:
            status = "[bright_green]✓  OK[/bright_green]" if ok else "[bright_red]✗  ERROR[/bright_red]"
            table.add_row(name, status, detail)

        console.print()
        console.print(table)
        console.print()
    else:
        print("\nEstado del Sistema:")
        for name, ok, detail in checks:
            print(f"  {'✓' if ok else '✗'}  {name}: {detail}")
        print()

    all_ok = all(ok for _, ok, _ in checks)
    if not all_ok:
        print("⛔  Hay errores de configuración. Corrígelos antes de ejecutar el pipeline.\n")
        sys.exit(1)
    else:
        print("✅  Sistema listo para ejecutar.\n") if not _RICH else console.print("  [bright_green]✅ Sistema listo para ejecutar.[/bright_green]\n")


def _make_review_callback():
    """
    Returns a human review callback for the CLI (non-TUI) mode.

    Displays the generated ticket and asks the PO to:
      - Press Enter / type 'a' / 'approve' → approve and save
      - Type feedback text → revise and show again
      - Type 'd' / 'discard' → cancel (raises KeyboardInterrupt)

    The callback signature matches what pipeline.run_pipeline() expects:
      (ticket_text: str, ticket_type: str, module: str, revision: int) -> str | None
    """
    def _callback(ticket_text: str, ticket_type: str, module: str, revision: int = 0) -> "str | None":
        label = "Revisión del PO" if revision == 0 else f"Revisión del PO (iteración {revision + 1})"

        if _RICH:
            from rich.panel import Panel as RPanel
            console.print()
            console.print(RPanel(
                ticket_text,
                title=f"[bold bright_cyan]{label} — {ticket_type} · {module}[/bold bright_cyan]",
                border_style="bright_cyan",
                padding=(1, 2),
            ))
            console.print()
            console.print("[dim]Opciones: [bright_green]Enter / 'a'[/bright_green] = aprobar  |  "
                          "[yellow]texto[/yellow] = feedback  |  "
                          "[red]'d'[/red] = descartar[/dim]")
            raw = console.input("[bright_cyan]▶ Tu decisión:[/bright_cyan] ").strip()
        else:
            separator = "-" * 60
            print(f"\n{separator}")
            print(f"  {label} — {ticket_type} · {module}")
            print(separator)
            print(ticket_text)
            print(separator)
            print("Opciones: Enter/'a' = aprobar | texto = dar feedback | 'd' = descartar")
            raw = input("▶ Tu decisión: ").strip()

        lower = raw.lower()

        if not lower or lower in ("a", "approve", "aprobar", "ok", "yes", "si", "sí"):
            return None   # PO approved — pipeline continues to save

        if lower in ("d", "discard", "descartar", "cancel", "cancelar", "n", "no"):
            print("\n⏹  Ticket descartado por el PO.\n")
            raise KeyboardInterrupt

        # Any other text is treated as feedback for the Escritor
        return raw

    return _callback


def get_input(args: argparse.Namespace) -> str:
    """Obtiene el input del PO — desde args o de forma interactiva."""
    if args.input:
        return " ".join(args.input)

    if _RICH:
        console.print("[bold white]Describe el requerimiento:[/bold white]")
        console.print("[dim](Escribe en lenguaje natural — el Orquestador lo clasificará)[/dim]\n")
        po_input = Prompt.ask("[bright_cyan]▶ Requerimiento[/bright_cyan]")
    else:
        print("Describe el requerimiento:")
        po_input = input("▶ ")

    if not po_input.strip():
        print("⛔  El requerimiento no puede estar vacío.\n")
        sys.exit(1)

    return po_input.strip()


def handle_error(e: Exception) -> None:
    """Maneja errores del pipeline con mensajes claros."""
    error_msg = str(e)

    if _RICH:
        if "BLOCKED_BY" in error_msg or "Pipeline bloqueado" in error_msg:
            console.print(Panel(
                error_msg,
                title="[bold yellow]⛔ PIPELINE BLOQUEADO[/bold yellow]",
                border_style="yellow",
            ))
        elif ("ANTHROPIC_API_KEY" in error_msg or "authentication" in error_msg.lower()
              or "API_KEY_INVALID" in error_msg or "API key not valid" in error_msg
              or "invalid api key" in error_msg.lower()):
            console.print(Panel(
                "Tu API key no es válida.\n\n"
                "Opciones para corregirlo:\n"
                "  [bright_cyan][0] Setup[/bright_cyan] → vuelve a ingresar tu key desde el wizard\n"
                "  o edita [cyan].env[/cyan] directamente y corrige el valor de tu API key.\n\n"
                "[dim]Google keys empiezan con AIza... · Anthropic con sk-ant-... · OpenAI con sk-...[/dim]",
                title="[bold red]⛔ API KEY INVÁLIDA[/bold red]",
                border_style="red",
            ))
        else:
            console.print(Panel(
                f"{type(e).__name__}: {error_msg}",
                title="[bold red]⛔ ERROR[/bold red]",
                border_style="red",
            ))
    else:
        print(f"\n⛔ ERROR: {error_msg}\n")


# ─── Modo Jira ────────────────────────────────────────────────────────────────

def _run_jira_mode(issue_ref: str, review_callback=None) -> None:
    """
    Flujo completo con Jira como origen y destino:
      1. Lee el issue de Jira (título + descripción)
      2. Corre el pipeline con ese contexto (+ revisión humana si review_callback está definido)
      3. Actualiza la descripción del issue con la US/DT estructurada
      4. Agrega un comentario de confirmación
    """
    if not JIRA_ENABLED:
        print("\n⛔  Jira no está configurado en el .env\n"
              "   Completa: JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN\n"
              "   Genera tu token en: https://id.atlassian.com/manage-profile/security/api-tokens\n")
        sys.exit(1)

    from utils.jira_client import JiraClient, JiraAPIError, _normalize_key

    try:
        issue_key = _normalize_key(issue_ref)
    except ValueError as e:
        print(f"\n⛔  {e}\n")
        sys.exit(1)

    jira = JiraClient(JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN)

    # ── 1. Leer issue ──────────────────────────────────────────────────────────
    print(f"\n🔗 Leyendo Jira: {issue_key}...")
    try:
        issue = jira.get_issue(issue_key)
    except JiraAPIError as e:
        print(f"\n⛔  Error al leer el issue de Jira: {e}\n")
        sys.exit(1)
    except RuntimeError as e:
        print(f"\n⛔  {e}\n")
        sys.exit(1)

    linked   = issue.get("linked_issues", [])
    labels   = issue.get("labels", [])
    comps    = issue.get("components", [])
    comments = issue.get("recent_comments", [])
    epic_k   = issue.get("epic_key", "")
    epic_s   = issue.get("epic_summary", "")
    par_k    = issue.get("parent_key", "")
    par_s    = issue.get("parent_summary", "")

    print(f"   ✓ {issue['key']}: {issue['summary']}")
    print(f"   Tipo: {issue['issue_type']} → pipeline: {issue['pipeline_type']} | Proyecto: {issue['project_key']} | Estado: {issue['status']}")
    if issue.get("type_warning"):
        print(f"   {issue['type_warning']}")
    if labels:    print(f"   Labels: {', '.join(labels)}")
    if comps:     print(f"   Componentes: {', '.join(comps)}")
    if epic_k:    print(f"   Épica: {epic_k} — {epic_s}")
    if par_k:     print(f"   Parent: {par_k} — {par_s}")
    if linked:
        print(f"   Vinculadas: {len(linked)} incidencia(s)")
        for lnk in linked:
            print(f"     • [{lnk['relation']}] {lnk['key']} ({lnk['type']}) — {lnk['summary']} [{lnk['status']}]")
    if comments:  print(f"   Comentarios recientes: {len(comments)}")

    # ── 1b. Epic siblings + sprint goal (contexto adicional desde Jira) ────────
    epic_siblings: list[dict] = []
    sprint_info:   dict       = {}

    if epic_k:
        print(f"   🔍 Buscando siblings en épica {epic_k}...")
        try:
            siblings_raw = jira.get_epic_children(epic_k, max_results=8)
            # Excluir el propio issue del resultado
            epic_siblings = [s for s in siblings_raw if s["key"] != issue["key"]]
            if epic_siblings:
                print(f"   ✓ Siblings encontrados: {len(epic_siblings)}")
        except Exception:
            pass  # best-effort

    print(f"   🔍 Buscando sprint activo de {issue['project_key']}...")
    try:
        sprint_info = jira.get_sprint_goal(issue["project_key"])
        if sprint_info.get("name"):
            print(f"   ✓ Sprint: {sprint_info['name']}")
        else:
            print(f"   — Sprint activo no encontrado (el board puede ser Kanban o sin permisos de Agile API)")
    except Exception:
        pass  # best-effort
    print()

    # ── 2. Construir el input para el pipeline ─────────────────────────────────
    meta_lines = []
    if labels:   meta_lines.append(f"Labels: {', '.join(labels)}")
    if comps:    meta_lines.append(f"Componentes: {', '.join(comps)}")
    if epic_k:   meta_lines.append(f"Épica: {epic_k} — {epic_s}")
    if par_k:    meta_lines.append(f"Issue padre: {par_k} — {par_s}")
    meta_section = ("\n\nMetadatos del issue:\n" + "\n".join(meta_lines)) if meta_lines else ""

    linked_section = ""
    if linked:
        lines = []
        for lnk in linked:
            header = f"  [{lnk['relation']}] {lnk['key']} ({lnk['type']}) — {lnk['summary']} [{lnk['status']}]"
            lines.append(header)
            desc = lnk.get("description", "").strip()
            if desc:
                for dline in desc.split("\n")[:20]:
                    if dline.strip():
                        lines.append(f"    {dline}")
        linked_section = "\n\nIncidencias vinculadas (con descripción completa):\n" + "\n".join(lines)

    # Epic siblings: otros tickets en la misma épica — contexto de qué ya se construyó
    siblings_section = ""
    if epic_siblings:
        lines = [
            f"  {s['key']} ({s['issue_type']}) [{s['status']}] — {s['summary']}"
            for s in epic_siblings
        ]
        siblings_section = (
            f"\n\nOtros tickets de la misma épica ({epic_k} — {epic_s}):\n"
            + "\n".join(lines)
            + "\n(Usa esta lista para evitar duplicados, identificar dependencias y entender "
              "el alcance ya construido de la épica.)"
        )

    # Sprint goal: objetivo del sprint activo — ancla el ticket al contexto del equipo
    sprint_section = ""
    if sprint_info.get("goal"):
        sprint_section = (
            f"\n\nSprint activo: {sprint_info.get('name', '')}\n"
            f"Objetivo del sprint: {sprint_info['goal']}\n"
            f"(Verifica que este ticket sea coherente con el objetivo del sprint actual.)"
        )

    comments_section = ""
    if comments:
        lines = [f"  [{c['author']}]: {c['body'][:400]}" for c in comments[:5]]
        comments_section = "\n\nComentarios recientes (contexto del equipo):\n" + "\n".join(lines)

    po_input = (
        f"[JIRA: {issue['key']}]\n"
        f"Título: {issue['summary']}\n"
        f"Tipo en Jira: {issue['issue_type']} (genera: {issue['pipeline_type']})\n"
        f"Proyecto: {issue['project_key']}\n"
        f"{meta_section}\n\n"
        f"Descripción del issue:\n{issue['description'] or '(Sin descripción)'}"
        f"{sprint_section}"
        f"{siblings_section}"
        f"{linked_section}"
        f"{comments_section}"
    )

    # ── 3. Correr el pipeline ──────────────────────────────────────────────────
    try:
        run = asyncio.run(run_pipeline(
            po_input,
            jira_issue_key=issue_key,
            human_review_callback=review_callback,
        ))
    except KeyboardInterrupt:
        print("\n\n⏹  Pipeline cancelado por el usuario.\n")
        sys.exit(0)
    except Exception as e:
        handle_error(e)
        sys.exit(1)

    # ── 4. Escribir resultado de vuelta a Jira ─────────────────────────────────
    if not hasattr(run, "ticket_content") or not run.ticket_content:
        print("\n⚠️  El pipeline no retornó contenido para actualizar Jira.\n")
        return

    print(f"\n📤 Publicando en Jira: {issue_key}...")

    try:
        # Actualizar descripción con la US/DT estructurada
        jira.update_description(issue_key, run.ticket_content)
        print(f"   ✓ Descripción actualizada")

        # Agregar comentario de confirmación
        comment_body = (
            f"h3. Openspired — Ticket estructurado\n\n"
            f"*Pipeline ejecutado:* {run.ticket_id}\n"
            f"*Archivo local:* +{run.file_path}+\n\n"
            f"La descripción de este issue fue enriquecida automáticamente por el pipeline "
            f"de agentes. Revisa y ajusta antes de mover a \"In Progress\"."
        )
        comment_id = jira.add_comment(issue_key, comment_body)
        print(f"   ✓ Comentario agregado (ID: {comment_id})")
        print(f"\n✅ {issue_key} actualizado en Jira.\n")

    except JiraAPIError as e:
        print(f"\n⚠️  Error al escribir en Jira: {e}")
        print(f"   El ticket fue guardado localmente en: {run.file_path}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python run.py",
        description="Openspired — Pipeline Multi-Agente",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Ejemplos:
              python run.py
              python run.py "Agregar sección de logs al módulo Support"
              python run.py --check
        """),
    )
    parser.add_argument(
        "input",
        nargs="*",
        help="Requerimiento del PO (si se omite, se pedirá interactivamente)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verificar configuración del sistema sin ejecutar el pipeline",
    )
    parser.add_argument(
        "--jira",
        metavar="ISSUE_KEY",
        help="Lee el input desde un issue de Jira y escribe el resultado de vuelta. "
             "Acepta clave (CAKE-123) o URL completa.",
    )
    parser.add_argument(
        "--serve-api",
        action="store_true",
        help="Levanta la API local para desktop/UI en 127.0.0.1:8765",
    )
    args = parser.parse_args()

    print_header()

    if args.serve_api:
        try:
            import uvicorn
            from api_server import app
        except ImportError as e:
            print(f"\n⛔  Dependencia faltante para API local: {e}")
            print("   Instala: pip install fastapi uvicorn\n")
            sys.exit(1)
        print("🚀 Iniciando API local en http://127.0.0.1:8765 ...")
        uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
        return

    if args.check:
        print_check()
        return

    # ── Modo Jira ──────────────────────────────────────────────────────────────
    if args.jira:
        _run_jira_mode(args.jira, review_callback=_make_review_callback())
        return

    # ── Modo normal ────────────────────────────────────────────────────────────
    po_input = get_input(args)

    _pipeline_run = None
    try:
        _pipeline_run = asyncio.run(run_pipeline(
            po_input,
            human_review_callback=_make_review_callback(),
        ))
    except KeyboardInterrupt:
        print("\n\n⏹  Ticket descartado por el PO.")
        # Correr Meta-Observador para capturar anti-patrones del rechazo
        if _pipeline_run is not None:
            try:
                asyncio.run(run_meta_on_rejection(_pipeline_run, rejection_reason="Descartado por el PO"))
            except Exception:
                pass
        sys.exit(0)
    except Exception as e:
        handle_error(e)
        sys.exit(1)


if __name__ == "__main__":
    main()
