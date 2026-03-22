"""
setup_wizard.py — Interactive product onboarding for Openspired.

Runs automatically on first launch (no workspace configured).
Guides the user through product setup in plain language — no technical knowledge needed.
Generates all workspace context files from templates.

New in this version:
  - Language selection first (EN / ES) — entire system adapts
  - Ticket structure extraction from Jira (auto-detects format from real tickets)
  - Fallback: manual ticket format description when Jira isn't available
"""
from __future__ import annotations
import json
import os
import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

try:
    from config import PROJECT_ROOT, WORKSPACE_DIR, PROFILE_ROOT, AGENTS_DIR
except Exception:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    WORKSPACE_DIR = PROJECT_ROOT / "workspace"
    PROFILE_ROOT = PROJECT_ROOT
    AGENTS_DIR = PROJECT_ROOT / "agents"

TEMPLATES_DIR = PROJECT_ROOT / "templates"

_RICH = False
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    from rich.rule import Rule
    console = Console()
    _RICH = True
except ImportError:
    class _FakeConsole:
        def print(self, *a, **kw): print(*[str(x) for x in a])
        def rule(self, *a, **kw): print("─" * 40)
    console = _FakeConsole()


# ─── i18n strings ─────────────────────────────────────────────────────────────

_T = {
    "en": {
        "welcome_title":   "Welcome to Openspired",
        "welcome_body":    "This quick setup (~5 min) configures the AI agents for your product.\nYou only need to do this once.",
        "lang_prompt":     "Language / Idioma",
        "lang_choices":    ["English", "Español"],
        "s1_title":        "Step 1 of 6 — Your Product",
        "s1_hint":         "Tell us about what you're building.",
        "product_name":    "Product name",
        "product_desc":    "What does it do? (1-2 sentences)",
        "platform_prompt": "Main platform",
        "platform_choices":["Web Desktop", "Mobile", "Web + Mobile", "API / Backend", "Other"],
        "s2_title":        "Step 2 of 6 — Users & Roles",
        "s2_hint":         "Who uses your product and what can they do?",
        "default_roles_q": "Use standard roles? BASIC (view only) and FULL (view + edit)",
        "role_names":      "Role names",
        "role_can_do":     "What can a '{role}' do?",
        "s3_title":        "Step 3 of 6 — Product Modules",
        "s3_hint":         "What are the main sections or modules of your product?\nThese are the areas your team will create tickets for.",
        "modules_prompt":  "Module names",
        "module_does":     "What does '{module}' do? (one line)",
        "s4_title":        "Step 4 of 6 — Your Team",
        "s4_hint":         "Who's on the team? (press Enter to skip any role)",
        "po_name":         "Product Owner name",
        "designer":        "Designer name",
        "frontend":        "Frontend developer",
        "backend":         "Backend developer",
        "qa":              "QA Engineer",
        "comm_tool":       "Team communication tool",
        "s5_title":        "Step 5 of 6 — Ticket Structure",
        "s5_hint":         "Openspired learns your ticket format so every generated ticket matches your team's style.",
        "jira_learn_q":    "Do you have Jira configured? I can learn your ticket format automatically.",
        "jira_fetching":   "Fetching recent tickets from Jira to learn your format...",
        "jira_found":      "Found {n} tickets. Analyzing structure...",
        "jira_learned":    "✓ Ticket structure learned from your Jira history.",
        "jira_failed":     "Couldn't connect to Jira. Let's set up the format manually.",
        "manual_format_q": "Describe your ticket format",
        "manual_format_hint": "Example: 'User Story: As a [role] I want [action]. Acceptance Criteria as a numbered list. No bilingual.'",
        "manual_sections": "What sections does a ticket have?",
        "manual_sections_hint": "e.g. Goal, Acceptance Criteria, Notes",
        "manual_lang":     "Are your tickets in one language or bilingual?",
        "manual_lang_choices": ["One language only", "Bilingual (EN + ES)", "Other"],
        "s6_title":        "Step 6 of 6 — A Few Quick Rules",
        "s6_hint":         "These help the agents write better tickets for your team.",
        "excluded_plat":   "Any platform the agents should NEVER design for?",
        "log_rule":        "What actions should be logged?",
        "log_default":     "create, edit, delete",
        "domain_notes":    "Any other rule the agents must always follow? (optional)",
        "generating":      "Generating your workspace...",
        "done_title":      "✅ Setup Complete",
        "done_body":       "{name} is ready!\n\n✓  workspace/context/ ({n_modules} modules)\n✓  Ticket template saved\n✓  Language: {language}\n\n[dim]Edit workspace/context/ anytime to update your settings.[/dim]",
        "done_hint":       "Select [1] Generate ticket to create your first one.",
        "ticket_tmpl_default": "As a [Role]\nI want to [Action]\nSo that [Value]\n\nACCEPTANCE CRITERIA\n* [Criterion 1]\n* [Criterion 2]\n* [Criterion 3]\n\nNOTES\n* [Optional notes]",
    },
    "es": {
        "welcome_title":   "Bienvenido a Openspired",
        "welcome_body":    "Esta configuración (~5 min) prepara los agentes de IA para tu producto.\nSolo necesitas hacerlo una vez.",
        "lang_prompt":     "Language / Idioma",
        "lang_choices":    ["English", "Español"],
        "s1_title":        "Paso 1 de 6 — Tu Producto",
        "s1_hint":         "Cuéntanos qué estás construyendo.",
        "product_name":    "Nombre del producto",
        "product_desc":    "¿Qué hace? (1-2 oraciones)",
        "platform_prompt": "Plataforma principal",
        "platform_choices":["Web Desktop", "Móvil", "Web + Móvil", "API / Backend", "Otro"],
        "s2_title":        "Paso 2 de 6 — Usuarios y Roles",
        "s2_hint":         "¿Quién usa tu producto y qué puede hacer?",
        "default_roles_q": "¿Usar roles estándar? BASIC (solo ver) y FULL (ver + editar)",
        "role_names":      "Nombres de roles",
        "role_can_do":     "¿Qué puede hacer un '{role}'?",
        "s3_title":        "Paso 3 de 6 — Módulos del Producto",
        "s3_hint":         "¿Cuáles son las secciones principales de tu producto?\nEstas son las áreas para las que crearás tickets.",
        "modules_prompt":  "Nombres de módulos",
        "module_does":     "¿Qué hace '{module}'? (una línea)",
        "s4_title":        "Paso 4 de 6 — Tu Equipo",
        "s4_hint":         "¿Quién está en el equipo? (Enter para omitir)",
        "po_name":         "Nombre del Product Owner",
        "designer":        "Nombre del Diseñador",
        "frontend":        "Desarrollador Frontend",
        "backend":         "Desarrollador Backend",
        "qa":              "QA Engineer",
        "comm_tool":       "Herramienta de comunicación del equipo",
        "s5_title":        "Paso 5 de 6 — Estructura del Ticket",
        "s5_hint":         "Openspired aprende tu formato de ticket para que cada uno generado coincida con el estilo de tu equipo.",
        "jira_learn_q":    "¿Tienes Jira configurado? Puedo aprender tu formato de ticket automáticamente.",
        "jira_fetching":   "Obteniendo tickets recientes de Jira para aprender tu formato...",
        "jira_found":      "Encontré {n} tickets. Analizando estructura...",
        "jira_learned":    "✓ Estructura de ticket aprendida de tu historial de Jira.",
        "jira_failed":     "No se pudo conectar a Jira. Configuremos el formato manualmente.",
        "manual_format_q": "Describe tu formato de ticket",
        "manual_format_hint": "Ej: 'Historia de usuario: Como [rol] quiero [acción]. Criterios de aceptación en lista. Sin bilingüe.'",
        "manual_sections": "¿Qué secciones tiene un ticket?",
        "manual_sections_hint": "ej. Objetivo, Criterios de Aceptación, Notas",
        "manual_lang":     "¿Tus tickets están en un idioma o son bilingües?",
        "manual_lang_choices": ["Un solo idioma", "Bilingüe (EN + ES)", "Otro"],
        "s6_title":        "Paso 6 de 6 — Algunas Reglas Rápidas",
        "s6_hint":         "Ayudan a los agentes a escribir mejores tickets para tu equipo.",
        "excluded_plat":   "¿Hay alguna plataforma para la que los agentes NUNCA deben diseñar?",
        "log_rule":        "¿Qué acciones deben registrarse en logs?",
        "log_default":     "crear, editar, eliminar",
        "domain_notes":    "¿Alguna otra regla que los agentes siempre deben seguir? (opcional)",
        "generating":      "Generando tu workspace...",
        "done_title":      "✅ Configuración Completa",
        "done_body":       "¡{name} está listo!\n\n✓  workspace/context/ ({n_modules} módulos)\n✓  Plantilla de ticket guardada\n✓  Idioma: {language}\n\n[dim]Edita workspace/context/ cuando quieras actualizar tu configuración.[/dim]",
        "done_hint":       "Selecciona [1] Generar ticket para crear el primero.",
        "ticket_tmpl_default": "Como [Rol]\nQuiero [Acción]\nPara [Valor]\n\nCRITERIOS DE ACEPTACIÓN\n* [Criterio 1]\n* [Criterio 2]\n* [Criterio 3]\n\nNOTAS\n* [Notas opcionales]",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    val = _T.get(lang, _T["en"]).get(key, _T["en"].get(key, key))
    return val.format(**kwargs) if kwargs else val


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ask(prompt: str, default: str = "", required: bool = False, lang: str = "en") -> str:
    if _RICH:
        console.print("  [dim](← 'back' to go back)[/dim]")
    while True:
        if _RICH:
            val = Prompt.ask(f"  [bold cyan]{prompt}[/bold cyan]", default=default).strip()
        else:
            display = f"{prompt}" + (f" [{default}]" if default else "") + ": "
            val = input(f"  {display}").strip() or default
        if val.lower() in ("back", "atrás", "atras"):
            return _BACK
        if val or not required:
            return val
        msg = "This field is required." if lang == "en" else "Este campo es requerido."
        console.print(f"  [yellow]{msg}[/yellow]")


def _ask_list(prompt: str, example: str = "", lang: str = "en", default: list | None = None) -> list[str]:
    sep = "comma-separated" if lang == "en" else "separados por coma"
    hint = f" ({sep}, e.g. {example})" if example else f" ({sep})"
    default_str = ", ".join(default) if default else ""
    raw = _ask(f"{prompt}{hint}", default=default_str, lang=lang)
    if raw == _BACK:
        return [_BACK]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _ask_bool(question: str, default: bool = True, lang: str = "en") -> bool | str:
    """
    Pregunta booleana con soporte de navegación hacia atrás.
    Retorna True/False, o _BACK si el usuario escribe 'back'/'atrás'.
    """
    yes_label = "Y/n" if default else "y/N"
    back_hint = "back=regresar" if lang == "en" else "back=regresar"

    if _RICH:
        console.print(f"  [dim]({back_hint})[/dim]")
        raw = Prompt.ask(
            f"  [bold cyan]{question}[/bold cyan]",
            default="y" if default else "n",
        ).strip().lower()
    else:
        ans_hint = f" [{yes_label}, back]: "
        raw = input(f"  {question}{ans_hint}").strip().lower()

    if raw in ("back", "atrás", "atras"):
        return _BACK
    if default:
        return raw not in ("n", "no")
    return raw in ("y", "yes", "si", "sí", "s")


def _section(title: str):
    console.print()
    if _RICH:
        console.rule(f"[bold bright_cyan]{title}[/bold bright_cyan]")
    else:
        print(f"\n── {title} ─────────────────────────────")
    console.print()


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ─── Back navigation sentinel ─────────────────────────────────────────────────
_BACK = "__BACK__"


def _load_existing_state() -> dict:
    """
    Read existing workspace files and return a pre-filled state dict.
    Called at the start of run_wizard() so re-running setup shows previous values as defaults.
    """
    state: dict = {}
    ctx = WORKSPACE_DIR / "context"

    # ── preferences.md ───────────────────────────────────────────────────────
    try:
        for line in (ctx / "preferences.md").read_text(encoding="utf-8").split("\n"):
            if line.startswith("product_name:"):
                state["product_name"] = line.split(":", 1)[1].strip()
    except Exception:
        pass

    # ── global.md → platform, excluded_platforms, log_rule, domain_notes ─────
    try:
        glb = (ctx / "global.md").read_text(encoding="utf-8")
        for line in glb.split("\n"):
            if "**Plataforma principal:**" in line or "**Primary platform:**" in line:
                state["platform"] = line.split(":", 1)[1].strip()
            elif "**No desarrollar para:**" in line or "**No development for:**" in line:
                state["excluded_platforms"] = line.split(":", 1)[1].strip()
        m = re.search(r"(?:Solo registrar|Only log)[^\n]*?transac[^\n]*?: (.+?)\.", glb)
        if m:
            state["log_rule"] = m.group(1).strip()
        conv = re.search(r"##[^\n]*(?:Convenciones|Conventions)[^\n]*\n(.*?)(?=\n##|\Z)", glb, re.DOTALL)
        if conv:
            notes = [l.lstrip("- ").strip() for l in conv.group(1).split("\n") if l.strip().startswith("-")]
            notes = [n for n in notes if "Add your" not in n and "agrega" not in n.lower() and n != "(configurar aquí)" and n != "(configure here)"]
            if notes:
                state["domain_notes"] = "\n".join(notes)
    except Exception:
        pass

    # ── product_knowledge.md → product_desc, modules, module_lines ───────────
    try:
        pk = (ctx / "product_knowledge.md").read_text(encoding="utf-8")
        desc_m = re.search(r"##[^\n]*(?:Qué es|What is)[^\n]*\n+(.+?)(?=\n##)", pk, re.DOTALL)
        if desc_m:
            state["product_desc"] = desc_m.group(1).strip()
        module_names = re.findall(r"^### (.+)$", pk, re.MULTILINE)
        if module_names:
            state["modules"] = module_names
            module_lines = []
            for mn in module_names:
                blk = re.search(rf"### {re.escape(mn)}\n(.*?)(?=\n###|\Z)", pk, re.DOTALL)
                module_lines.append(f"### {mn}\n{blk.group(1).rstrip()}\n" if blk else f"### {mn}\n- **What it does:** (to be described)\n")
            state["module_lines"] = module_lines
    except Exception:
        pass

    # ── team.md → po_name, designer, frontend, backend, qa_name, comm_tool ───
    try:
        team = (ctx / "team.md").read_text(encoding="utf-8")
        for line in team.split("\n"):
            if "|" in line and "---" not in line and "Nombre" not in line and "Name" not in line and "Rol" not in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    name, role = parts[0], parts[1].lower()
                    if "product owner" in role:
                        state["po_name"] = name
                    elif "diseñ" in role or "design" in role:
                        state["designer"] = name
                    elif "frontend" in role:
                        state["frontend"] = name
                    elif "backend" in role:
                        state["backend"] = name
                    elif "qa" in role:
                        state["qa_name"] = name
        comm = re.search(r"(?:Herramienta de Comunicación|Communication Tool)\n- (.+)", team)
        if comm:
            state["comm_tool"] = comm.group(1).strip()
    except Exception:
        pass

    # ── ticket_template.md ────────────────────────────────────────────────────
    try:
        state["ticket_template"] = (ctx / "ticket_template.md").read_text(encoding="utf-8")
    except Exception:
        pass

    return state


def _set_env_line(env_text: str, key: str, value: str) -> str:
    """Replace or append a KEY=value line in .env text."""
    lines = env_text.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return "\n".join(lines)
    lines.append(f"{key}={value}")
    return "\n".join(lines)


# ─── Check if setup is needed ─────────────────────────────────────────────────

def needs_setup() -> bool:
    return not (WORKSPACE_DIR / "context" / "global.md").exists()


def load_language() -> str:
    """Read language preference from workspace. Defaults to 'en'."""
    prefs = WORKSPACE_DIR / "context" / "preferences.md"
    if prefs.exists():
        for line in prefs.read_text().split("\n"):
            if line.startswith("language:"):
                return line.split(":")[1].strip()
    return "en"


# ─── Ticket structure extraction from Jira ────────────────────────────────────

def _extract_ticket_template_from_jira(lang: str) -> str | None:
    """
    Connect to Jira and fetch recent tickets to infer the team's ticket format.
    Returns a template string or None if extraction fails.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(PROFILE_ROOT / ".env")
        import os
        base_url  = os.getenv("JIRA_BASE_URL", "")
        email     = os.getenv("JIRA_EMAIL", "")
        token     = os.getenv("JIRA_API_TOKEN", "")
        proj_key  = os.getenv("JIRA_PROJECT_KEY", "")

        # Check for placeholders
        placeholders = {"TU_EMPRESA", "TU_EMAIL", "TU_JIRA", "your-company", "your@email"}
        if not all([base_url, email, token]) or any(p in base_url for p in placeholders):
            return None

        # ── Health-check rápido antes de hacer cualquier otra llamada ────────
        # Verifica que las credenciales sean válidas antes de intentar extraer tickets.
        # Esto da al usuario un error claro inmediato en lugar de un timeout tardío.
        import urllib.request, urllib.parse, base64, json as _json
        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        _health_url = f"{base_url.rstrip('/')}/rest/api/3/myself"
        _health_req = urllib.request.Request(_health_url, headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(_health_req, timeout=10) as _hr:
                _hdata = _json.loads(_hr.read())
                _display_name = _hdata.get("displayName", email)
            _ok_msg = f"✓ Conectado a Jira como {_display_name}" if lang == "es" else f"✓ Connected to Jira as {_display_name}"
            console.print(f"  [green]{_ok_msg}[/green]")
        except urllib.error.HTTPError as _he:
            _err_body = _he.read().decode("utf-8", errors="ignore")[:200]
            _cred_err = (
                f"Error de credenciales Jira (HTTP {_he.code}): verifica tu email y API token."
                if lang == "es" else
                f"Jira credential error (HTTP {_he.code}): check your email and API token."
            )
            console.print(f"\n  [red]{_cred_err}[/red]")
            if _he.code in (401, 403):
                console.print(f"  [dim]{_err_body}[/dim]")
                return None
        except Exception as _he:
            console.print(f"\n  [red]No se pudo conectar a Jira:[/red] [dim]{_he}[/dim]\n")
            return None

        # Import Jira client
        sys.path.insert(0, str(PROJECT_ROOT / "engine"))
        from utils.jira_client import JiraClient

        jira = JiraClient(base_url, email, token)

        console.print(f"  [dim]{t(lang, 'jira_fetching')}[/dim]")

        # Search for recent issues with descriptions
        import urllib.request, urllib.parse, base64, json as _json
        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        jql = f"project = {proj_key} AND description is not EMPTY ORDER BY created DESC" if proj_key \
              else "description is not EMPTY ORDER BY created DESC"
        url = f"{base_url.rstrip('/')}/rest/api/3/search/jql?jql={urllib.parse.quote(jql)}&maxResults=5&fields=description,issuetype,summary"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read())
        except urllib.error.HTTPError as e:
            _body = e.read().decode("utf-8", errors="ignore")[:300]
            console.print(f"\n  [red]Jira HTTP {e.code} {e.reason}[/red]")
            console.print(f"  [dim]{_body}[/dim]\n")
            return None
        except Exception as e:
            console.print(f"\n  [red]Jira connection error:[/red] [dim]{e}[/dim]\n")
            return None

        issues = data.get("issues", [])
        if not issues:
            _no_tickets = "No tickets found — check your project key." if lang == "en" else "No se encontraron tickets — verifica la clave de proyecto."
            console.print(f"  [yellow]{_no_tickets}[/yellow]")
            return None

        console.print(f"  [dim]{t(lang, 'jira_found', n=len(issues))}[/dim]")

        # Extract descriptions and analyze structure
        descriptions = []
        for issue in issues:
            desc = issue.get("fields", {}).get("description")
            if desc:
                from utils.jira_client import _adf_to_text
                text = _adf_to_text(desc)
                if text and len(text) > 50:
                    descriptions.append(text)

        if not descriptions:
            return None

        # Detect common structural patterns
        template = _infer_template_from_descriptions(descriptions, lang)
        console.print(f"  [green]{t(lang, 'jira_learned')}[/green]")
        return template

    except Exception as e:
        console.print(f"\n  [red]Unexpected error:[/red] [dim]{e}[/dim]\n")
        return None


def _infer_template_from_descriptions(descriptions: list[str], lang: str) -> str:
    """
    Analyze a list of ticket descriptions and extract the common structure.
    Returns a template string with placeholders.
    """
    # Detect common section headers across descriptions
    section_pattern = re.compile(r'^([A-Z][A-Z\s/&]{2,40})$|^(\*\*[^*]+\*\*)$|^(#{1,3}\s.+)$',
                                 re.MULTILINE)

    all_sections: dict[str, int] = {}
    for desc in descriptions:
        found = section_pattern.findall(desc)
        for groups in found:
            header = next((g.strip("#* ") for g in groups if g), None)
            if header:
                all_sections[header] = all_sections.get(header, 0) + 1

    # Find sections that appear in at least 2 tickets (consistent patterns)
    consistent = [s for s, count in all_sections.items() if count >= 2]

    # Detect bilingual pattern
    is_bilingual = any("ESPAÑOL" in d or "español" in d.lower() or "SPANISH" in d for d in descriptions)

    # Detect "As a ... I want ... So that" pattern
    has_user_story = any(
        re.search(r'[Aa]s a\b|[Cc]omo\s+\w+', d) for d in descriptions
    )

    # Build the template
    lines = []

    if has_user_story:
        if lang == "es" or is_bilingual:
            lines += ["Como [Rol]", "Quiero [Acción]", "Para [Valor]", ""]
        else:
            lines += ["As a [Role]", "I want to [Action]", "So that [Value]", ""]

    # Add detected sections
    if consistent:
        for section in consistent[:6]:  # max 6 sections
            lines.append(f"{'─'*40}")
            lines.append(section.upper())
            lines.append(f"{'─'*40}")
            lines.append("* [Item 1]")
            lines.append("* [Item 2]")
            lines.append("")
    else:
        # Fallback generic template
        if lang == "es":
            lines += [
                "─" * 40, "CRITERIOS DE ACEPTACIÓN", "─" * 40,
                "* [Criterio 1]", "* [Criterio 2]", "",
                "─" * 40, "FLUJOS CRÍTICOS", "─" * 40,
                "* [Flujo 1]", "",
            ]
        else:
            lines += [
                "─" * 40, "ACCEPTANCE CRITERIA", "─" * 40,
                "* [Criterion 1]", "* [Criterion 2]", "",
                "─" * 40, "CRITICAL FLOWS", "─" * 40,
                "* [Flow 1]", "",
            ]

    if is_bilingual:
        separator = "════════════════════════════════ ESPAÑOL ════════════════════════════════"
        lines += [
            "", separator, "",
            "(Mirror of the English block in Spanish)",
        ]

    return "\n".join(lines)


# ─── Bootstrap: Historical context from Jira ──────────────────────────────────

def _bootstrap_historico_from_jira(lang: str, product_name: str) -> bool:
    """
    Fetch 6 months of completed Jira tickets and use AI to generate
    workspace/context/Contexto_Historico_Proyecto.md with real team patterns.
    Returns True on success, False on any failure (always safe to skip).
    """
    try:
        from dotenv import load_dotenv as _lde
        _lde(PROFILE_ROOT / ".env", override=True)
        import os as _os
        base_url = _os.getenv("JIRA_BASE_URL", "").strip()
        email    = _os.getenv("JIRA_EMAIL", "").strip()
        token    = _os.getenv("JIRA_API_TOKEN", "").strip()
        proj_key = _os.getenv("JIRA_PROJECT_KEY", "").strip()
        provider = _os.getenv("PROVIDER", "anthropic").lower()
        model    = _os.getenv("DEFAULT_MODEL", "claude-haiku-4-5-20251001")

        _BAD = {"TU_EMPRESA", "TU_EMAIL", "TU_JIRA", "your-company", "your@email"}
        if not all([base_url, email, token]) or any(p in v for p in _BAD for v in [base_url, email]):
            return False

        # ── Fetch completed tickets ───────────────────────────────────────────
        import urllib.request, base64, json as _json, urllib.parse
        from datetime import datetime as _dt, timedelta

        six_months_ago = (_dt.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        done_statuses = "Done, Finalizada, Cerrada, Released, 'To Be Released', Closed, Completed"
        jql = (
            f"project = {proj_key} AND status in ({done_statuses}) "
            f"AND created >= '{six_months_ago}' ORDER BY created DESC"
        ) if proj_key else (
            f"status in ({done_statuses}) AND created >= '{six_months_ago}' ORDER BY created DESC"
        )

        auth = base64.b64encode(f"{email}:{token}".encode()).decode()
        url = (
            f"{base_url.rstrip('/')}/rest/api/3/search/jql"
            f"?jql={urllib.parse.quote(jql)}&maxResults=200"
            f"&fields=summary,issuetype,assignee,status,created"
        )
        req = urllib.request.Request(url, headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = _json.loads(resp.read())

        issues = data.get("issues", [])
        if not issues:
            return False

        n = len(issues)
        msg = (f"  [dim]Analyzing {n} tickets with AI (~30 sec)...[/dim]"
               if lang == "en" else
               f"  [dim]Analizando {n} tickets con IA (~30 seg)...[/dim]")
        console.print(msg)

        # ── Build compact ticket list ─────────────────────────────────────────
        rows = []
        for issue in issues[:150]:  # cap to stay within token limits
            f = issue.get("fields", {})
            key      = issue.get("key", "?")
            itype    = f.get("issuetype", {}).get("name", "?")
            assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
            status   = f.get("status", {}).get("name", "?")
            summary  = f.get("summary", "")
            rows.append(f"[{key}][{itype}][{status}][{assignee}]: {summary}")
        tickets_block = "\n".join(rows)

        # ── Analysis prompt ───────────────────────────────────────────────────
        lang_instr = "Respond in English." if lang == "en" else "Responde en español."
        prompt = f"""You are analyzing {n} completed tickets from a software product team.
Product: {product_name}

TICKETS (key, type, status, assignee, summary):
{tickets_block}

Based ONLY on this data, generate a structured Markdown document with:

1. **Team & Roles** — Each person found in assignee data: name, ticket count, inferred role (PO / Designer / Frontend / Backend / QA).
2. **Product Modules / Areas** — Group tickets into feature clusters. For each: name, ticket count, one-line description.
3. **Completed Epics** — Major initiatives that appear finished (majority in Done/Closed).
4. **Active Epics** — Themes still being worked on.
5. **Writing Conventions** — 3–5 observable patterns in how this team writes tickets (naming style, bilingual or not, common structures).
6. **Platform & Domain Rules** — Any platform rules implied by the data (e.g., "Desktop only", role names).

Rules: Do NOT invent. Only extract what is clearly visible. Be concise — this is read by AI agents.
{lang_instr}"""

        # ── Call AI provider (uses same urllib approach as the main pipeline) ──
        result_text = None

        if provider == "anthropic":
            key = _os.getenv("ANTHROPIC_API_KEY", "")
            if key and "sk-ant-..." not in key and len(key) > 20:
                try:
                    import anthropic as _ant
                    client = _ant.Anthropic(api_key=key)
                    resp = client.messages.create(
                        model=model, max_tokens=4096,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    result_text = resp.content[0].text
                except Exception as _ae:
                    console.print(f"  [red]AI error (Anthropic): {_ae}[/red]")

        elif provider == "openai":
            key = _os.getenv("OPENAI_API_KEY", "")
            if key and "sk-..." not in key and len(key) > 20:
                try:
                    import urllib.request as _ureq, urllib.error as _uerr
                    _ourl = "https://api.openai.com/v1/chat/completions"
                    _opayload = _json.dumps({
                        "model": model,
                        "max_tokens": 4096,
                        "messages": [{"role": "user", "content": prompt}],
                    }).encode("utf-8")
                    _oreq = _ureq.Request(
                        _ourl,
                        data=_opayload,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        method="POST",
                    )
                    with _ureq.urlopen(_oreq, timeout=120) as _oresp:
                        _obody = _json.loads(_oresp.read().decode("utf-8"))
                        _choices = _obody.get("choices") or []
                        if _choices:
                            result_text = _choices[0]["message"]["content"]
                        else:
                            console.print(f"  [red]AI error (OpenAI): respuesta sin choices[/red]")
                except _uerr.HTTPError as _oe:
                    _oerr = _oe.read().decode("utf-8", errors="replace")
                    console.print(f"  [red]AI error (OpenAI {_oe.code}): {_oerr[:200]}[/red]")
                except Exception as _oe:
                    console.print(f"  [red]AI error (OpenAI): {_oe}[/red]")

        elif provider == "google":
            # Uses urllib REST — same as providers/google_prov.py, no SDK needed
            key = _os.getenv("GOOGLE_API_KEY", "")
            if key and "AIza..." not in key and len(key) > 20:
                try:
                    import urllib.request as _ureq, urllib.error as _uerr
                    _gurl = (
                        f"https://generativelanguage.googleapis.com/v1beta/models"
                        f"/{model}:generateContent?key={key}"
                    )
                    _gpayload = _json.dumps({
                        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.3},
                    }).encode("utf-8")
                    _greq = _ureq.Request(
                        _gurl, data=_gpayload,
                        headers={"content-type": "application/json"},
                        method="POST",
                    )
                    with _ureq.urlopen(_greq, timeout=120) as _gresp:
                        _gbody = _json.loads(_gresp.read().decode("utf-8"))
                        result_text = _gbody["candidates"][0]["content"]["parts"][0]["text"]
                except _uerr.HTTPError as _ge:
                    _gerr = _ge.read().decode("utf-8", errors="replace")
                    console.print(f"  [red]AI error (Google {_ge.code}): {_gerr[:200]}[/red]")
                except Exception as _ge:
                    console.print(f"  [red]AI error (Google): {_ge}[/red]")

        if not result_text:
            console.print("  [yellow]⚠ Bootstrap incompleto: no se obtuvo respuesta de la IA.[/yellow]")
            console.print("  [dim]Verifica que tu API key sea válida y el modelo esté disponible.[/dim]")
            return False

        # ── Write Contexto_Historico_Proyecto.md ─────────────────────────────
        today = datetime.now().strftime("%Y-%m-%d")
        if lang == "en":
            header = (
                f"# PROJECT HISTORICAL CONTEXT — {product_name}\n"
                f"## Generated: {today} | Source: Jira Bootstrap ({n} tickets, last 6 months)\n"
                f"## Auto-enriched by: Meta-Observer after each approved ticket\n\n"
                f"> Bootstrapped automatically from Jira history.\n"
                f"> The Meta-Observer ENRICHES this file after each run — it never replaces it.\n"
                f"> Edit sections directly to correct or add information.\n\n---\n\n"
            )
        else:
            header = (
                f"# CONTEXTO HISTÓRICO DEL PROYECTO — {product_name}\n"
                f"## Generado: {today} | Fuente: Bootstrap de Jira ({n} tickets, últimos 6 meses)\n"
                f"## Auto-enriquecido por: Meta-Observador tras cada ticket aprobado\n\n"
                f"> Generado automáticamente desde el historial de Jira.\n"
                f"> El Meta-Observador ENRIQUECE este archivo tras cada corrida — nunca lo reemplaza.\n"
                f"> Edita secciones directamente para corregir o agregar información.\n\n---\n\n"
            )

        out_path = WORKSPACE_DIR / "context" / "Contexto_Historico_Proyecto.md"
        _write(out_path, header + result_text)
        return True

    except Exception as _ex:
        console.print(f"  [red]Bootstrap error: {_ex}[/red]")
        return False


# ─── Step 0: API key collection ───────────────────────────────────────────────

def _ensure_api_key(lang: str) -> None:
    """
    Step 0 — Collect AI provider + key if not already configured.
    Writes directly to .env — the user never needs to open a text editor.
    Safe to call multiple times: silently skips if a valid key already exists.
    """
    env_path = PROFILE_ROOT / ".env"
    _PLACEHOLDERS = {
        "your_anthropic_key_here", "your_google_api_key_here",
        "your_openai_key_here", "sk-ant-...", "sk-...", "AIza...",
        "", "your_key_here",
    }

    def _get_val(content: str, key: str) -> str:
        for line in content.split("\n"):
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
        return ""

    def _is_valid(k: str) -> bool:
        return bool(k) and k not in _PLACEHOLDERS and len(k) > 15

    current_env = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    provider = _get_val(current_env, "PROVIDER") or "google"

    _KEY_VARS = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai":    "OPENAI_API_KEY",
        "google":    "GOOGLE_API_KEY",
    }
    # Skip if current provider or any provider already has a valid key
    if _is_valid(_get_val(current_env, _KEY_VARS.get(provider, "GOOGLE_API_KEY"))):
        return
    if any(_is_valid(_get_val(current_env, v)) for v in _KEY_VARS.values()):
        return

    # ── Show provider selection ───────────────────────────────────────────────
    step_title = "AI Key — Step 0 / 6" if lang == "en" else "API Key — Paso 0 / 6"
    _section(step_title)

    if _RICH:
        intro = (
            "[dim]Openspired needs an AI key to run. Pick one provider — you only need ONE key.[/dim]"
            if lang == "en" else
            "[dim]Openspired necesita una API key para funcionar. Elige un proveedor — solo necesitas UNA key.[/dim]"
        )
        console.print(f"  {intro}\n")
        console.print("  [bright_cyan][1][/bright_cyan]  [bold]Google Gemini Flash[/bold]  "
                      "[green]← cheapest · free tier available[/green]")
        console.print("     [dim]$0.10 / $0.40 per 1M tokens  ·  https://aistudio.google.com/apikey[/dim]\n")
        console.print("  [bright_cyan][2][/bright_cyan]  Anthropic Claude Haiku")
        console.print("     [dim]$0.80 / $4.00 per 1M tokens  ·  https://console.anthropic.com/settings/keys[/dim]\n")
        console.print("  [bright_cyan][3][/bright_cyan]  OpenAI GPT-4o Mini")
        console.print("     [dim]$0.15 / $0.60 per 1M tokens  ·  https://platform.openai.com/api-keys[/dim]\n")
        choice = Prompt.ask("  ▶", choices=["1", "2", "3"], default="1")
    else:
        print("\n  AI Provider:")
        print("  [1] Google Gemini Flash  ← cheapest, free tier  ($0.10/$0.40 per 1M tokens)")
        print("  [2] Anthropic Claude Haiku                       ($0.80/$4.00 per 1M tokens)")
        print("  [3] OpenAI GPT-4o Mini                           ($0.15/$0.60 per 1M tokens)")
        choice = input("  ▶ [1]: ").strip() or "1"

    _PROVIDERS = {
        "1": ("google",    "GOOGLE_API_KEY",    "gemini-2.5-flash-lite",    "https://aistudio.google.com/apikey"),
        "2": ("anthropic", "ANTHROPIC_API_KEY", "claude-haiku-4-5-20251001","https://console.anthropic.com/settings/keys"),
        "3": ("openai",    "OPENAI_API_KEY",    "gpt-4o-mini",             "https://platform.openai.com/api-keys"),
    }
    chosen_provider, chosen_var, chosen_model, key_url = _PROVIDERS.get(choice, _PROVIDERS["1"])

    # ── Ask for the key ───────────────────────────────────────────────────────
    console.print()
    url_hint = f"  [dim]Get your free key at: {key_url}[/dim]" if _RICH else f"  Get your key at: {key_url}"
    console.print(url_hint)
    console.print()

    api_key = ""
    try:
        import getpass
        label = "Paste your API key (hidden)" if lang == "en" else "Pega tu API key (oculta)"
        if _RICH:
            console.print(f"  [bold cyan]{label}[/bold cyan]")
        api_key = getpass.getpass("  ▶ ").strip()
    except Exception:
        label = "Paste your API key" if lang == "en" else "Pega tu API key"
        api_key = _ask(label, lang=lang)

    if not _is_valid(api_key):
        skip_msg = (
            "⚠ No key entered — skipping. Edit .env or re-run Setup to add it later."
            if lang == "en" else
            "⚠ Sin key — omitiendo. Edita .env o ejecuta Setup de nuevo para agregarla."
        )
        console.print(f"\n  [yellow]{skip_msg}[/yellow]")
        return

    # ── Write PROVIDER, MODEL and KEY to .env ────────────────────────────────
    new_env = current_env
    new_env = _set_env_line(new_env, "PROVIDER",      chosen_provider)
    new_env = _set_env_line(new_env, "DEFAULT_MODEL",  chosen_model)
    new_env = _set_env_line(new_env, chosen_var,       api_key)
    env_path.write_text(new_env, encoding="utf-8")

    ok_msg = (
        f"✓ {chosen_provider.capitalize()} configured — key saved to .env"
        if lang == "en" else
        f"✓ {chosen_provider.capitalize()} configurado — key guardada en .env"
    )
    console.print(f"\n  [green]{ok_msg}[/green]")


# ─── Main wizard ──────────────────────────────────────────────────────────────

def run_wizard():
    os.system("clear" if os.name != "nt" else "cls")

    # Print logo
    try:
        from utils.logo import print_logo
        print_logo(lang="en")  # logo always in EN (it's a proper name)
    except Exception:
        pass

    # ── Language selection (FIRST — everything adapts from here) ────────────────
    if _RICH:
        console.print(Panel(
            "[bold bright_cyan]Language / Idioma[/bold bright_cyan]\n\n"
            "[dim]Choose the language for your workspace and all generated tickets.[/dim]\n"
            "[dim]Elige el idioma para tu workspace y todos los tickets generados.[/dim]",
            border_style="bright_cyan",
            padding=(1, 3),
        ))
        console.print()
        console.print("  [bright_cyan][1][/bright_cyan]  English")
        console.print("  [bright_cyan][2][/bright_cyan]  Español")
        console.print()
        lang_choice = Prompt.ask("  ▶", choices=["1", "2"], default="1")
        lang = "en" if lang_choice == "1" else "es"
    else:
        print("\n  Language / Idioma")
        print("  [1] English   [2] Español")
        raw = input("  ▶ ").strip()
        lang = "es" if raw == "2" else "en"

    os.system("clear" if os.name != "nt" else "cls")
    try:
        from utils.logo import print_logo
        print_logo(lang=lang)
    except Exception:
        pass

    # Welcome panel
    if _RICH:
        console.print(Panel(
            f"[bold bright_cyan]{t(lang, 'welcome_title')}[/bold bright_cyan]\n\n"
            f"[dim]{t(lang, 'welcome_body')}[/dim]",
            border_style="bright_cyan",
            padding=(1, 3),
        ))
    else:
        print(f"\n{t(lang, 'welcome_title')}")
        print(t(lang, "welcome_body") + "\n")

    # ── Step 0: API key ────────────────────────────────────────────────────────
    _ensure_api_key(lang)

    # ── Steps 1-6: Step-indexed loop with back navigation ──────────────────────
    _back_hint_msg = "  (type 'back' at any text prompt to go to the previous step)" if lang == "en" else "  (escribe 'back' en cualquier campo de texto para volver al paso anterior)"
    console.print(f"\n  [dim]{_back_hint_msg}[/dim]" if _RICH else f"\n{_back_hint_msg}")

    # Load existing workspace data → pre-fills all steps on re-run
    _s = _load_existing_state()

    step = 1
    while step <= 6:

        # ── Step 1: Product basics ───────────────────────────────────────────────
        if step == 1:
            _section(t(lang, "s1_title"))
            console.print(f"  [dim]{t(lang, 's1_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's1_hint')}\n")

            product_name = _ask(t(lang, "product_name"), default=_s.get("product_name", ""), required=True, lang=lang)
            if product_name == _BACK: step = max(1, step - 1); continue

            product_desc = _ask(t(lang, "product_desc"), default=_s.get("product_desc", ""), required=True, lang=lang)
            if product_desc == _BACK: step = max(1, step - 1); continue

            if _RICH:
                platform = Prompt.ask(
                    f"  [bold cyan]{t(lang, 'platform_prompt')}[/bold cyan]",
                    choices=t(lang, "platform_choices"),
                    default=_s.get("platform", t(lang, "platform_choices")[0]),
                )
            else:
                choices = t(lang, "platform_choices")
                for i, c in enumerate(choices, 1):
                    print(f"  [{i}] {c}")
                idx = input(f"  {t(lang, 'platform_prompt')} [1]: ").strip()
                platform = choices[int(idx) - 1] if idx.isdigit() and 0 < int(idx) <= len(choices) else choices[0]

            _s.update({"product_name": product_name, "product_desc": product_desc, "platform": platform})
            step += 1

        # ── Step 2: Roles ────────────────────────────────────────────────────────
        elif step == 2:
            _section(t(lang, "s2_title"))
            console.print(f"  [dim]{t(lang, 's2_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's2_hint')}\n")

            product_name = _s["product_name"]
            platform     = _s["platform"]

            use_default_roles = _ask_bool(t(lang, "default_roles_q"), default=True, lang=lang)

            if use_default_roles:
                if lang == "es":
                    roles_text = "- **BASIC:** Solo lectura. No puede crear, editar ni configurar.\n- **FULL:** Acceso completo. Puede crear, editar y configurar."
                else:
                    roles_text = "- **BASIC:** View-only. Cannot create, edit, or configure.\n- **FULL:** Full access. Can create, edit, and configure."
            else:
                role_names = _ask_list(t(lang, "role_names"), "Admin, Viewer, Editor", lang=lang)
                if role_names == [_BACK]: step = max(1, step - 1); continue
                role_descs = []
                _backed = False
                for r in role_names:
                    desc = _ask(t(lang, "role_can_do", role=r), lang=lang)
                    if desc == _BACK:
                        _backed = True
                        break
                    role_descs.append(f"- **{r}:** {desc}")
                if _backed: step = max(1, step - 1); continue
                roles_text = "\n".join(role_descs)

            _s.update({"roles_text": roles_text})
            step += 1

        # ── Step 3: Modules ──────────────────────────────────────────────────────
        elif step == 3:
            _section(t(lang, "s3_title"))
            console.print(f"  [dim]{t(lang, 's3_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's3_hint')}\n")

            modules_raw = _ask_list(t(lang, "modules_prompt"), "Dashboard, Users, Billing, Settings", lang=lang, default=_s.get("modules"))
            if modules_raw == [_BACK]: step = max(1, step - 1); continue

            modules = modules_raw if modules_raw else ["Main"]

            # Build lookup of existing module descriptions for pre-fill
            _existing_descs: dict[str, str] = {}
            for _ml in _s.get("module_lines", []):
                _mn_m = re.match(r"### (.+)", _ml)
                _desc_m = re.search(r"\*\*(?:¿Qué hace\?|What it does)\*\*: (.+)", _ml)
                if _mn_m and _desc_m:
                    _existing_descs[_mn_m.group(1).strip()] = _desc_m.group(1).strip()

            module_lines = []
            _backed = False
            for m in modules:
                console.print(f"\n  [bold]{m}[/bold]" if _RICH else f"\n  {m}")
                _prev_desc = _existing_descs.get(m, "")
                what = _ask(f"  {t(lang, 'module_does', module=m)}", default=_prev_desc, lang=lang)
                if what == _BACK:
                    _backed = True
                    break
                module_lines.append(
                    f"### {m}\n"
                    f"- **{'¿Qué hace?' if lang == 'es' else 'What it does'}:** {what or '(to be described)'}\n"
                    f"- **{'Acciones clave' if lang == 'es' else 'Key actions'}:** (fill in after first tickets)\n"
                    f"- **{'Límites' if lang == 'es' else 'Limits'}:** (fill in after first tickets)\n"
                    f"- **{'Patrón UX' if lang == 'es' else 'UX Pattern'}:** (table, form, modal — fill in after design)\n"
                )
            if _backed: step = max(1, step - 1); continue

            _s.update({"modules": modules, "module_lines": module_lines})
            step += 1

        # ── Step 4: Team ─────────────────────────────────────────────────────────
        elif step == 4:
            _section(t(lang, "s4_title"))
            console.print(f"  [dim]{t(lang, 's4_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's4_hint')}\n")

            po_name   = _ask(t(lang, "po_name"),    default=_s.get("po_name", ""),   lang=lang)
            if po_name == _BACK: step = max(1, step - 1); continue
            designer  = _ask(t(lang, "designer"),   default=_s.get("designer", ""),  lang=lang)
            if designer == _BACK: step = max(1, step - 1); continue
            frontend  = _ask(t(lang, "frontend"),   default=_s.get("frontend", ""),  lang=lang)
            if frontend == _BACK: step = max(1, step - 1); continue
            backend   = _ask(t(lang, "backend"),    default=_s.get("backend", ""),   lang=lang)
            if backend == _BACK: step = max(1, step - 1); continue
            qa_name   = _ask(t(lang, "qa"),         default=_s.get("qa_name", ""),   lang=lang)
            if qa_name == _BACK: step = max(1, step - 1); continue
            comm_tool = _ask(t(lang, "comm_tool"),  default=_s.get("comm_tool", "Slack"), lang=lang)
            if comm_tool == _BACK: step = max(1, step - 1); continue

            _s.update({"po_name": po_name, "designer": designer, "frontend": frontend,
                       "backend": backend, "qa_name": qa_name, "comm_tool": comm_tool})
            step += 1

        # ── Step 5: Ticket structure ─────────────────────────────────────────────
        elif step == 5:
            _section(t(lang, "s5_title"))
            console.print(f"  [dim]{t(lang, 's5_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's5_hint')}\n")

            ticket_template = None

            # Try auto-extraction from Jira
            has_jira = _ask_bool(t(lang, "jira_learn_q"), default=True, lang=lang)
            if has_jira:
                # Check if Jira credentials exist in .env
                from dotenv import load_dotenv as _load_dotenv
                _load_dotenv(PROFILE_ROOT / ".env", override=False)
                _jira_url   = os.getenv("JIRA_BASE_URL", "")
                _jira_email = os.getenv("JIRA_EMAIL", "")
                _jira_token = os.getenv("JIRA_API_TOKEN", "")
                _jira_proj  = os.getenv("JIRA_PROJECT_KEY", "")
                _placeholders = {"TU_EMPRESA", "TU_EMAIL", "TU_JIRA", "your-company", "your@email", ""}

                _creds_missing = (
                    not all([_jira_url, _jira_email, _jira_token])
                    or any(p in _jira_url for p in _placeholders)
                )

                if _creds_missing:
                    # Collect credentials inline
                    _url_hint  = "Tu URL de Jira (ej. https://tuempresa.atlassian.net)" if lang == "es" else "Your Jira URL (e.g. https://yourcompany.atlassian.net)"
                    _mail_hint = "Email con el que entras a Jira" if lang == "es" else "Email you use to log into Jira"
                    _tok_hint  = "API Token (créalo en https://id.atlassian.com/manage-profile/security/api-tokens)" if lang == "es" else "API Token (create one at https://id.atlassian.com/manage-profile/security/api-tokens)"
                    _proj_hint = "Clave del proyecto Jira (ej. PROD, DEV — visible en la URL del board)" if lang == "es" else "Jira project key (e.g. PROD, DEV — visible in your board URL)"

                    console.print()
                    if _RICH:
                        _creds_label = "Credenciales de Jira" if lang == "es" else "Jira Credentials"
                        console.print(f"  [bold bright_cyan]{_creds_label}[/bold bright_cyan]")
                        console.print(f"  [dim]{'Necesito estos datos para conectarme a tu Jira.' if lang == 'es' else 'I need these to connect to your Jira.'}\n[/dim]")
                    else:
                        print(f"\n  {'Jira credentials needed:' if lang == 'en' else 'Credenciales de Jira necesarias:'}\n")

                    _jira_url_in   = _ask(_url_hint,  default=_jira_url,   required=True, lang=lang)
                    if _jira_url_in == _BACK:
                        has_jira = False
                    else:
                        _jira_email_in = _ask(_mail_hint, default=_jira_email, required=True, lang=lang)
                        if _jira_email_in == _BACK:
                            has_jira = False
                        else:
                            import getpass as _gp
                            console.print(f"  [bold cyan]{_tok_hint}[/bold cyan]" if _RICH else f"  {_tok_hint}")
                            try:
                                _jira_token_in = _gp.getpass("  Token (hidden): ")
                            except Exception:
                                _jira_token_in = input("  Token: ").strip()

                            if not _jira_token_in:
                                has_jira = False
                            else:
                                _jira_proj_in = _ask(_proj_hint, default=_jira_proj, lang=lang)
                                if _jira_proj_in == _BACK:
                                    has_jira = False
                                else:
                                    # Save to .env
                                    _env_path = PROFILE_ROOT / ".env"
                                    _env_txt  = _env_path.read_text(encoding="utf-8") if _env_path.exists() else ""
                                    _env_txt  = _set_env_line(_env_txt, "JIRA_BASE_URL",    _jira_url_in.rstrip("/"))
                                    _env_txt  = _set_env_line(_env_txt, "JIRA_EMAIL",       _jira_email_in)
                                    _env_txt  = _set_env_line(_env_txt, "JIRA_API_TOKEN",   _jira_token_in)
                                    if _jira_proj_in:
                                        _env_txt = _set_env_line(_env_txt, "JIRA_PROJECT_KEY", _jira_proj_in.upper())
                                    _env_path.write_text(_env_txt, encoding="utf-8")
                                    # Reload env so _extract_ticket_template_from_jira picks up new values
                                    os.environ["JIRA_BASE_URL"]    = _jira_url_in.rstrip("/")
                                    os.environ["JIRA_EMAIL"]       = _jira_email_in
                                    os.environ["JIRA_API_TOKEN"]   = _jira_token_in
                                    if _jira_proj_in:
                                        os.environ["JIRA_PROJECT_KEY"] = _jira_proj_in.upper()
                                    _saved_msg = "✓ Credenciales de Jira guardadas en .env" if lang == "es" else "✓ Jira credentials saved to .env"
                                    console.print(f"  [green]{_saved_msg}[/green]\n")

                if has_jira:
                    ticket_template = _extract_ticket_template_from_jira(lang)
                    if not ticket_template:
                        if _RICH:
                            console.print(f"\n  [yellow]{t(lang, 'jira_failed')}[/yellow]\n")
                        else:
                            print(f"\n  {t(lang, 'jira_failed')}\n")

            # Manual fallback
            if not ticket_template:
                console.print()
                fmt_desc = _ask(t(lang, "manual_format_q"), lang=lang)
                if fmt_desc == _BACK: step = max(1, step - 1); continue
                sections_raw = _ask_list(
                    t(lang, "manual_sections"),
                    t(lang, "manual_sections_hint"),
                    lang=lang,
                )
                if sections_raw == [_BACK]: step = max(1, step - 1); continue

                if _RICH:
                    manual_lang_choices = t(lang, "manual_lang_choices")
                    console.print(f"\n  [bold cyan]{t(lang, 'manual_lang')}[/bold cyan]")
                    for i, c in enumerate(manual_lang_choices, 1):
                        console.print(f"     [bright_cyan][{i}][/bright_cyan]  {c}")
                    ml_choice = Prompt.ask("     ▶", choices=["1", "2", "3"], default="1")
                    ml_idx = int(ml_choice) - 1
                else:
                    print(f"\n  {t(lang, 'manual_lang')}")
                    manual_lang_choices = t(lang, "manual_lang_choices")
                    for i, c in enumerate(manual_lang_choices, 1):
                        print(f"  [{i}] {c}")
                    raw = input("  ▶ ").strip()
                    ml_idx = int(raw) - 1 if raw.isdigit() else 0

                is_bilingual = ml_idx == 1

                tmpl_lines = []
                if lang == "es":
                    tmpl_lines += ["Como [Rol]", "Quiero [Acción]", "Para [Valor]", ""]
                else:
                    tmpl_lines += ["As a [Role]", "I want to [Action]", "So that [Value]", ""]

                for s in (sections_raw or (["ACCEPTANCE CRITERIA", "NOTES"] if lang == "en" else ["CRITERIOS DE ACEPTACIÓN", "NOTAS"])):
                    tmpl_lines += [f"{'─'*40}", s.upper(), f"{'─'*40}", "* [Item 1]", "* [Item 2]", ""]

                if is_bilingual:
                    tmpl_lines += [
                        "", "════════════════════════════════ ESPAÑOL ════════════════════════════════", "",
                        "(Mirror of the English block in Spanish)", "",
                    ]

                ticket_template = "\n".join(tmpl_lines)

                if fmt_desc:
                    ticket_template = f"# FORMAT NOTES\n{fmt_desc}\n\n# TEMPLATE\n{ticket_template}"

            _s.update({"ticket_template": ticket_template, "has_jira": has_jira})
            step += 1

        # ── Step 6: Conventions ──────────────────────────────────────────────────
        elif step == 6:
            _section(t(lang, "s6_title"))
            console.print(f"  [dim]{t(lang, 's6_hint')}[/dim]\n" if _RICH else f"  {t(lang, 's6_hint')}\n")

            platform = _s["platform"]

            excluded_platforms = _ask(
                t(lang, "excluded_plat"),
                default=_s.get("excluded_platforms", "Mobile" if "Desktop" in platform else ""),
                lang=lang,
            )
            if excluded_platforms == _BACK: step = max(1, step - 1); continue

            log_rule = _ask(t(lang, "log_rule"), default=_s.get("log_rule", t(lang, "log_default")), lang=lang)
            if log_rule == _BACK: step = max(1, step - 1); continue

            domain_notes = _ask(t(lang, "domain_notes"), lang=lang)
            if domain_notes == _BACK: step = max(1, step - 1); continue

            _s.update({"excluded_platforms": excluded_platforms, "log_rule": log_rule, "domain_notes": domain_notes})
            step += 1

        else:
            step += 1  # safety

    # ── Unpack state for the rest of the function ──────────────────────────────
    product_name       = _s["product_name"]
    product_desc       = _s["product_desc"]
    platform           = _s["platform"]
    roles_text         = _s["roles_text"]
    modules            = _s["modules"]
    module_lines       = _s["module_lines"]
    po_name            = _s.get("po_name", "")
    designer           = _s.get("designer", "")
    frontend           = _s.get("frontend", "")
    backend            = _s.get("backend", "")
    qa_name            = _s.get("qa_name", "")
    comm_tool          = _s.get("comm_tool", "Slack")
    ticket_template    = _s["ticket_template"]
    excluded_platforms = _s.get("excluded_platforms", "")
    log_rule           = _s.get("log_rule", "")
    domain_notes       = _s.get("domain_notes", "")
    has_jira           = _s.get("has_jira", False)

    # ── Generate all workspace files ──────────────────────────────────────────
    _section(t(lang, "generating"))

    ctx = WORKSPACE_DIR / "context"
    rb  = ctx / ".reasoning_bank"

    # preferences.md
    prefs_content = (
        f"# OPENSPIRED PREFERENCES\n"
        f"language: {lang}\n"
        f"product_name: {product_name}\n"
        f"setup_date: {datetime.now().strftime('%Y-%m-%d')}\n"
    )

    # global.md (adapts to language)
    if lang == "es":
        global_content = f"""# REGLAS GLOBALES — {product_name}
## Alcance: Universal | Generado por: Openspired Setup | Fecha: {datetime.now().strftime('%Y-%m-%d')}

> Estas reglas aplican a TODOS los agentes en cada ejecución del pipeline.

---

## Plataforma
- **Plataforma principal:** {platform}
{"- **No desarrollar para:** " + excluded_platforms if excluded_platforms else ""}

## Roles de Usuario
{roles_text}

## Formato de Salida
- Los tickets siguen la plantilla definida en `workspace/context/ticket_template.md`.
- Solo texto plano estructurado — sin markup de Jira ({{panel}}, {{color}}, etc.).
- Máximo 6 criterios de aceptación por bloque.
- Máximo 3 flujos críticos por ticket.

## Reglas de Logs de Auditoría
- Solo registrar acciones transaccionales: {log_rule}.
- No registrar navegación ni acciones de solo lectura.

## Convenciones del Dominio
{"- " + domain_notes if domain_notes else "- (Agrega reglas específicas de tu producto aquí)"}
"""
    else:
        global_content = f"""# GLOBAL RULES — {product_name}
## Scope: Universal | Generated by: Openspired Setup | Date: {datetime.now().strftime('%Y-%m-%d')}

> These rules apply to ALL agents in every pipeline run.

---

## Platform
- **Primary platform:** {platform}
{"- **No development for:** " + excluded_platforms if excluded_platforms else ""}

## User Roles
{roles_text}

## Output Format
- Tickets follow the template defined in `workspace/context/ticket_template.md`.
- Plain text only — no Jira markup tags ({{panel}}, {{color}}, etc.).
- Max 6 acceptance criteria per block.
- Max 3 critical flows per ticket.

## Audit Log Rules
- Only log transactional actions: {log_rule}.
- Never log navigation or read-only actions.

## Domain Conventions
{"- " + domain_notes if domain_notes else "- (Add your product-specific rules here)"}
"""

    # team.md
    team_entries = []
    po_label   = "Product Owner" if lang == "en" else "Product Owner"
    des_label  = "Designer" if lang == "en" else "Diseñador"
    fe_label   = "Frontend Developer" if lang == "en" else "Desarrollador Frontend"
    be_label   = "Backend Developer" if lang == "en" else "Desarrollador Backend"
    qa_label   = "QA Engineer" if lang == "en" else "QA Engineer"

    if po_name:   team_entries.append(f"| {po_name} | {po_label} |")
    if designer:  team_entries.append(f"| {designer} | {des_label} |")
    if frontend:  team_entries.append(f"| {frontend} | {fe_label} |")
    if backend:   team_entries.append(f"| {backend} | {be_label} |")
    if qa_name:   team_entries.append(f"| {qa_name} | {qa_label} |")

    assign_rules = []
    if designer:  assign_rules.append(f"- {'Design Tasks' if lang == 'en' else 'Design Tasks'} → {designer}")
    if backend:   assign_rules.append(f"- {'Backend tickets' if lang == 'en' else 'Tickets backend'} → {backend}")
    if frontend:  assign_rules.append(f"- {'Frontend tickets' if lang == 'en' else 'Tickets frontend'} → {frontend}")

    team_title = "TEAM" if lang == "en" else "EQUIPO"
    assign_title = "Assignment Rules" if lang == "en" else "Reglas de Asignación"
    comm_title = "Communication Tool" if lang == "en" else "Herramienta de Comunicación"

    team_content = f"""# {team_title} — {product_name}
## Generated by: Openspired Setup | Date: {datetime.now().strftime('%Y-%m-%d')}

---

| {'Name' if lang == 'en' else 'Nombre'} | {'Role' if lang == 'en' else 'Rol'} |
|------|------|
{chr(10).join(team_entries) if team_entries else f"| ({'add your team here' if lang == 'en' else 'agrega tu equipo aquí'}) | Role |"}

## {comm_title}
- {comm_tool}

## {assign_title}
{chr(10).join(assign_rules) if assign_rules else ('- (configure here)' if lang == 'en' else '- (configurar aquí)')}
"""

    # product_knowledge.md
    module_block = "\n\n".join(module_lines)
    know_title = "PRODUCT KNOWLEDGE" if lang == "en" else "CONOCIMIENTO DEL PRODUCTO"
    know_note  = ("This file grows automatically. The Meta-Observer updates it after each approved ticket."
                  if lang == "en" else
                  "Este archivo crece automáticamente. El Meta-Observador lo actualiza tras cada ticket aprobado.")

    knowledge_content = f"""# {know_title} — {product_name}
## Generated by: Openspired Setup | Auto-updated by: Meta-Observer Agent

> {know_note}

---

## {'What is' if lang == 'en' else 'Qué es'} {product_name}?
{product_desc}

## {'Platform' if lang == 'en' else 'Plataforma'}
{platform}

## {'Main Modules' if lang == 'en' else 'Módulos Principales'}

{module_block}

---

## {'Integrations' if lang == 'en' else 'Integraciones'}
- ({'Add integrations as you build them' if lang == 'en' else 'Agrega integraciones a medida que las construyas'})

---

## {'Recent Changes' if lang == 'en' else 'Cambios Recientes'}
<!-- {'The Meta-Observer appends entries here after each ticket run.' if lang == 'en' else 'El Meta-Observador agrega entradas aquí tras cada corrida.'} -->
"""

    # sprint_context.md
    sprint_title = "SPRINT CONTEXT" if lang == "en" else "CONTEXTO DEL SPRINT"
    sprint_content = f"""# {sprint_title} — {product_name}
## {'Update this file at the start of each sprint.' if lang == 'en' else 'Actualiza este archivo al inicio de cada sprint.'}

---

## {'Current Sprint' if lang == 'en' else 'Sprint Actual'}
- **{'Name' if lang == 'en' else 'Nombre'}:** Sprint 1
- **{'Dates' if lang == 'en' else 'Fechas'}:** {datetime.now().strftime('%Y-%m-%d')} → ({'end date' if lang == 'en' else 'fecha de fin'})
- **{'Jira Project Keys' if lang == 'en' else 'Claves de Proyecto Jira'}:** ({'your project key' if lang == 'en' else 'tu clave de proyecto'})

## {'Active Epics' if lang == 'en' else 'Épicas Activas'}
- ({'Add your active epics here' if lang == 'en' else 'Agrega tus épicas activas aquí'})

## {'Goals This Sprint' if lang == 'en' else 'Objetivos del Sprint'}
- ({'What does the team aim to deliver?' if lang == 'en' else '¿Qué quiere entregar el equipo?'})
"""

    # ticket_template.md — the extracted or manual format
    tmpl_title = "TICKET TEMPLATE" if lang == "en" else "PLANTILLA DE TICKET"
    tmpl_note  = ("This template defines the structure of every generated ticket.\n"
                  "The Writer agent follows this exactly.\n"
                  "Edit this file to change your ticket format — changes take effect on the next run.\n"
                  "You can also update it via the [f] Feedback option during ticket review."
                  if lang == "en" else
                  "Esta plantilla define la estructura de cada ticket generado.\n"
                  "El agente Escritor la sigue exactamente.\n"
                  "Edita este archivo para cambiar tu formato — los cambios aplican en la siguiente corrida.\n"
                  "También puedes actualizarla con la opción [f] Feedback durante la revisión de tickets.")

    ticket_template_content = f"""# {tmpl_title} — {product_name}
## {'Source' if lang == 'en' else 'Fuente'}: {'Extracted from Jira / Manual setup' if lang == 'en' else 'Extraído de Jira / Configuración manual'}
## {'Last updated' if lang == 'en' else 'Última actualización'}: {datetime.now().strftime('%Y-%m-%d')}

> {tmpl_note}

---

{ticket_template}

---

## {'How to update this template' if lang == 'en' else 'Cómo actualizar esta plantilla'}
{'1. Edit this file directly, OR' if lang == 'en' else '1. Edita este archivo directamente, O'}
{'2. During ticket review, choose [f] Feedback and say "update template: [your new format]"' if lang == 'en' else '2. Durante la revisión de tickets, elige [f] Feedback y escribe "actualizar plantilla: [tu nuevo formato]"'}
"""

    # Reasoning bank stubs
    patterns_title = "SUCCESSFUL PATTERNS" if lang == "en" else "PATRONES EXITOSOS"
    anti_title = "ANTI-PATTERNS" if lang == "en" else "ANTI-PATRONES"
    fb_title = "HUMAN FEEDBACK LOG" if lang == "en" else "LOG DE FEEDBACK HUMANO"

    patterns_note = ("Patterns extracted from approved tickets. Auto-updated by the Meta-Observer."
                     if lang == "en" else
                     "Patrones extraídos de tickets aprobados. Auto-actualizado por el Meta-Observador.")
    anti_note = ("Mistakes to avoid. Auto-updated by the Meta-Observer."
                 if lang == "en" else
                 "Errores a evitar. Auto-actualizado por el Meta-Observador.")
    fb_note = ("Every piece of feedback you give during ticket review is stored here.\n"
               "Agents read this to understand your preferences and improve over time."
               if lang == "en" else
               "Cada feedback que das durante la revisión de tickets se guarda aquí.\n"
               "Los agentes lo leen para entender tus preferencias y mejorar con el tiempo.")

    patterns_content     = f"# {patterns_title} — {product_name}\n\n> {patterns_note}\n\n---\n\n<!-- {'Patterns appear here after approved tickets.' if lang == 'en' else 'Los patrones aparecen aquí tras los tickets aprobados.'} -->\n"
    antipatterns_content = f"# {anti_title} — {product_name}\n\n> {anti_note}\n\n---\n\n<!-- {'Anti-patterns appear here as the system learns.' if lang == 'en' else 'Los anti-patrones aparecen aquí mientras el sistema aprende.'} -->\n"
    feedback_content     = f"# {fb_title} — {product_name}\n\n> {fb_note}\n\n---\n\n<!-- {'Feedback entries appear here after ticket reviews.' if lang == 'en' else 'Las entradas de feedback aparecen aquí tras las revisiones.'} -->\n"

    # Write all files
    _write(ctx / "preferences.md",         prefs_content)
    _write(ctx / "global.md",              global_content)
    _write(ctx / "team.md",               team_content)
    _write(ctx / "product_knowledge.md",   knowledge_content)
    _write(ctx / "sprint_context.md",      sprint_content)
    _write(ctx / "ticket_template.md",     ticket_template_content)

    # Los archivos del reasoning_bank contienen aprendizajes acumulados del Meta-Observador.
    # Solo se crean si NO existen — nunca se sobreescriben en re-runs para no perder memoria.
    if not (rb / "patrones_exitosos.md").exists():
        _write(rb / "patrones_exitosos.md", patterns_content)
    if not (rb / "anti_patrones.md").exists():
        _write(rb / "anti_patrones.md",     antipatterns_content)
    if not (rb / "human_feedback.md").exists():
        _write(rb / "human_feedback.md",    feedback_content)

    # Module stubs
    for m in modules:
        # Sanitizar slug: remover caracteres problemáticos en rutas de filesystem
        import re as _re
        slug = m.lower()
        slug = _re.sub(r"[:\.\(\)\[\]{}\"'<>|?*\\]", "", slug)  # caracteres especiales
        slug = _re.sub(r"\s+", "-", slug)                        # espacios → guion
        slug = _re.sub(r"-{2,}", "-", slug)                      # guiones dobles
        slug = slug.strip("-")
        mod_path = WORKSPACE_DIR / "modules" / slug / "context.md"
        if not mod_path.exists():
            what_it_does = next(
                (ml.split("does:**")[1].split("\n")[0].strip()
                 for ml in module_lines if m in ml and "does:**" in ml),
                ""
            )
            mod_note = ("Agents write the DELTA — what changes — not a re-description of this baseline."
                        if lang == "en" else
                        "Los agentes escriben el DELTA — lo que cambia — no una re-descripción de esta base.")
            stub = (
                f"# {'MODULE CONTEXT' if lang == 'en' else 'CONTEXTO DEL MÓDULO'} — {m}\n"
                f"## {'Product' if lang == 'en' else 'Producto'}: {product_name} | "
                f"{'Generated' if lang == 'en' else 'Generado'}: {datetime.now().strftime('%Y-%m-%d')}\n\n"
                f"> {mod_note}\n\n---\n\n"
                f"## {'What This Module Does' if lang == 'en' else 'Qué Hace Este Módulo'}\n"
                f"{what_it_does or ('(to be described)' if lang == 'en' else '(por describir)')}\n\n"
                f"## {'Current Capabilities' if lang == 'en' else 'Capacidades Actuales'}\n"
                f"- ({'Will be populated after first tickets' if lang == 'en' else 'Se llenará tras los primeros tickets'})\n\n"
                f"## {'Business Rules' if lang == 'en' else 'Reglas de Negocio'}\n"
                f"- ({'Will be populated from approved tickets' if lang == 'en' else 'Se llenará desde tickets aprobados'})\n\n"
                f"---\n## {'Change Log' if lang == 'en' else 'Log de Cambios'}\n"
                f"| {'Date' if lang == 'en' else 'Fecha'} | Ticket | {'What changed' if lang == 'en' else 'Qué cambió'} |\n"
                f"|------|--------|------|\n"
                f"| {datetime.now().strftime('%Y-%m-%d')} | — | {'Initial stub' if lang == 'en' else 'Stub inicial'} |\n"
            )
            _write(mod_path, stub)

    # ── Generar Directorio_Equipo.md con datos reales del equipo ─────────────
    # Este archivo es leído por el Orquestador para asignar tickets.
    # Se genera con los nombres reales ingresados en el Step 4.
    _dir_path = AGENTS_DIR / "00_Orquestador" / "Directorio_Equipo.md"
    _dir_lines = [
        f"# EQUIPO DE PRODUCTO: DIRECTORIO Y ROLES",
        f"## Actualizado: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "> **Nota:** Generado automáticamente por el Setup Wizard.",
        "> El Orquestador consulta este directorio para asignar tickets.",
        "",
        "---",
        "",
        "## PRODUCT OWNER",
        f"- **{po_name or '(no configurado)'}** – PO Principal. Genera y revisa la mayoría de las historias.",
        "",
        "## DISEÑO",
        f"- **{designer or '(no configurado)'}** – Diseñador/a principal. Todas las Design Tasks van a esta persona.",
        "",
        "## DESARROLLO",
        f"- **{frontend or '(no configurado)'}** – Frontend / Fullstack.",
        f"- **{backend or '(no configurado)'}** – Tech Lead / Backend.",
        "",
        "## QA",
        f"- **{qa_name or '(no configurado)'}** – QA Engineer.",
        "",
        "## COMUNICACIÓN",
        f"- Herramienta principal: {comm_tool}",
        "",
        "---",
        "",
        "> **Nota:** Actualiza este archivo cada vez que el equipo cambie.",
    ]
    _write(_dir_path, "\n".join(_dir_lines) + "\n")

    # ── Bootstrap historical context from Jira (optional — needs API key) ────
    if has_jira:
        console.print()
        bq = (
            "Analyze your full ticket history to learn your team's patterns?"
            if lang == "en" else
            "¿Analizar tu historial de tickets para aprender los patrones del equipo?"
        )
        bn = (
            "(fetches last 6 months of completed tickets, ~30 sec)"
            if lang == "en" else
            "(obtiene últimos 6 meses de tickets terminados, ~30 seg)"
        )
        console.print(f"  [dim]{bn}[/dim]")
        do_bootstrap = _ask_bool(bq, default=True, lang=lang)
        if do_bootstrap:
            fetch_msg = (
                "  [dim]Fetching completed tickets from Jira...[/dim]"
                if lang == "en" else
                "  [dim]Obteniendo tickets terminados de Jira...[/dim]"
            )
            console.print(fetch_msg)
            ok = _bootstrap_historico_from_jira(lang, product_name)
            if ok:
                ok_msg = "✓ Historical context bootstrapped." if lang == "en" else "✓ Contexto histórico generado."
                console.print(f"  [green]{ok_msg}[/green]")
            else:
                skip_msg = (
                    "⚠ Skipped — add your API key to .env first, then re-run Setup."
                    if lang == "en" else
                    "⚠ Omitido — agrega tu API key en .env primero, luego ejecuta Setup de nuevo."
                )
                console.print(f"  [yellow]{skip_msg}[/yellow]")

    # ── Done ──────────────────────────────────────────────────────────────────
    lang_label = "English" if lang == "en" else "Español"
    console.print()
    if _RICH:
        console.print(Panel(
            t(lang, "done_body", name=product_name, n_modules=len(modules), language=lang_label),
            title=f"[bold green]{t(lang, 'done_title')}[/bold green]",
            border_style="green",
            padding=(1, 2),
        ))
        console.print()
        console.print(f"  [dim]{t(lang, 'done_hint')}[/dim]")
    else:
        print(f"\n✅ {product_name} is ready! ({len(modules)} modules, language: {lang_label})")
        print(t(lang, "done_hint"))

    console.print()

    # ── Pause before returning to the main menu ────────────────────────────────
    _continue_label = "Press Enter to open the main menu →" if lang == "en" else "Presiona Enter para abrir el menú principal →"
    if _RICH:
        console.print(f"  [bold bright_cyan]{_continue_label}[/bold bright_cyan]")
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    else:
        input(f"\n  {_continue_label} ")


if __name__ == "__main__":
    run_wizard()
