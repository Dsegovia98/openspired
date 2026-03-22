"""
context/builder.py — Context Discovery Protocol (CDP)

Builds the minimum necessary context for each agent using a layered
lookup strategy. Agents receive ONLY what they need — no context pollution.

Context layers (highest to lowest priority):
  1. Module context   → workspace/modules/{module}/context.md  (most specific)
  2. Product guide    → workspace/context/product_guide.md OR {DOMAIN}/Guia_Maestra_{DOMAIN}.md
  3. Product knowledge→ workspace/context/product_knowledge.md
  4. Sprint context   → workspace/context/sprint_context.md
  5. Universal rules  → workspace/context/global.md            (always present)
  6. Agent definition → agents/{AgentFolder}/{AgentFile}.md
  7. Agent skills     → agents/{AgentFolder}/Skills/*.md

If a layer is missing, it degrades gracefully — the agent proceeds with
what's available and documents its assumptions.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import config


# ─── Read helpers ─────────────────────────────────────────────────────────────

def _read(path: Path) -> Optional[str]:
    """Read a file. Returns None (not an error string) if it doesn't exist."""
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return None


def _read_workspace(rel: str) -> Optional[str]:
    """Read a file relative to workspace/."""
    return _read(config.WORKSPACE_DIR / rel)


def _read_agent(rel: str) -> Optional[str]:
    """Read a file relative to agents/ with profile override fallback."""
    for base in config.AGENT_SEARCH_DIRS:
        content = _read(base / rel)
        if content:
            return content
    return None


def _section(title: str, content: str) -> str:
    """Wrap content in a labeled section block for the LLM."""
    return f"\n\n{'='*60}\n## {title}\n{'='*60}\n{content}\n"


def _section_if(title: str, content: Optional[str]) -> str:
    """Only add a section if content exists."""
    if content:
        return _section(title, content)
    return ""


# ─── CDP: Product guide lookup ────────────────────────────────────────────────

def _product_guide() -> Optional[str]:
    """
    CDP Layer 2: Look up the product master guide (Guia_Maestra / product_guide).

    Search order (first match wins):
      1. workspace/context/product_guide.md          (canonical portable path)
      2. {DOMAIN_PRIMARY}/Guia_Maestra_{DOMAIN_PRIMARY}.md  (legacy domain path)

    This file is OBLIGATORIO for Dev Concepto and Escritor to understand the
    product's current screens, components, UX patterns, and module terminology.
    New users should populate workspace/context/product_guide.md via the
    setup wizard or manually.
    """
    candidates = [
        config.WORKSPACE_DIR / "context" / "product_guide.md",
        config.RUNTIME_PROJECT_ROOT / config.DOMAIN_PRIMARY / f"Guia_Maestra_{config.DOMAIN_PRIMARY}.md",
    ]
    for path in candidates:
        content = _read(path)
        if content:
            return content
    return None


# ─── CDP: Module context lookup ───────────────────────────────────────────────

def _module_context(module: Optional[str]) -> Optional[str]:
    """
    CDP Layer 1: Look up module-specific context.

    Search order:
      1. workspace/modules/{module}/context.md   (exact match)
      2. workspace/modules/{slug}/context.md     (slug: lowercase, spaces→dashes)

    Returns None if no module context exists yet (first time for this module).
    The Meta-Observer will create this file after the first approved ticket.
    """
    if not module:
        return None

    candidates = [
        config.WORKSPACE_DIR / "modules" / module / "context.md",
        config.WORKSPACE_DIR / "modules" / module.lower().replace(" ", "-") / "context.md",
        config.WORKSPACE_DIR / "modules" / module.lower().replace(" ", "_") / "context.md",
    ]
    for path in candidates:
        content = _read(path)
        if content:
            return content
    return None


# ─── Agent context definitions ────────────────────────────────────────────────
#
# Each entry: (section_title, path_resolver_fn)
# path_resolver_fn returns Optional[str] — None means "skip silently"
#
# CONVENTION:
#   _w("path")  → read from workspace/
#   _a("path")  → read from agents/
#

def _w(rel: str):
    return lambda: _read_workspace(rel)

def _a(rel: str):
    return lambda: _read_agent(rel)

def _recent_feedback() -> Optional[str]:
    """
    Returns the N most recent PO feedback entries (not the full log).
    Avoids token bloat from an unbounded-growth feedback file.
    """
    try:
        from utils.feedback import load_recent_feedback
        result = load_recent_feedback()
        return result if result else None
    except Exception:
        return None


AGENT_CONTEXT: dict[str, list[tuple[str, any]]] = {

    "orquestador": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("SPRINT CONTEXT",           _w("context/sprint_context.md")),
        ("PRODUCT KNOWLEDGE",        _w("context/product_knowledge.md")),
        ("TEAM DIRECTORY",           _w("context/team.md")),
        ("INTERFACE MAP",            _w("context/interface_map.md")),
        ("TICKET REGISTRY",          _w("logs/_Registro.md")),
        ("HISTORICAL CONTEXT",       _w("context/Contexto_Historico_Proyecto.md")),
        ("AGENT DEFINITION",         _a("00_Orquestador/00_Orquestador.md")),
        ("SKILL: TRIAGE",            _a("00_Orquestador/Skills/01_Skill_Triaje_Requerimientos.md")),
        ("SKILL: DECOMPOSITION",     _a("00_Orquestador/Skills/02_Skill_Deconstruccion_Epicas.md")),
        ("SKILL: HUMAN IN THE LOOP", _a("00_Orquestador/Skills/03_Skill_Human_in_the_Loop.md")),
    ],

    "ideador": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("PRODUCT KNOWLEDGE",        _w("context/product_knowledge.md")),
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("AGENT DEFINITION",         _a("02_Ideador/02_Ideador.md")),
        ("SKILL: VALUE EXPANSION",   _a("02_Ideador/Skills/01_Skill_Expansion_Valor.md")),
        ("SKILL: VISUAL ANALYSIS",   _a("02_Ideador/Skills/02_Skill_Analisis_Visual.md")),
    ],

    "researcher": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("PRODUCT KNOWLEDGE",        _w("context/product_knowledge.md")),
        ("ENTITY RELATIONSHIPS",     _w("context/relationships.md")),
        ("SPRINT CONTEXT",           _w("context/sprint_context.md")),
        ("HISTORICAL CONTEXT",       _w("context/Contexto_Historico_Proyecto.md")),
        ("ARCH DECISIONS",           _w("context/decisiones_arquitectura.md")),
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("AGENT DEFINITION",         _a("03_Researcher/03_Researcher.md")),
        ("SKILL: HISTORICAL SEARCH", _a("03_Researcher/Skills/01_Skill_Busqueda_Historica.md")),
        ("SKILL: MODULE BOOTSTRAP",  _a("03_Researcher/Skills/02_Skill_Bootstrap_Modulo.md")),
    ],

    "dev_concepto": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("SPRINT CONTEXT",           _w("context/sprint_context.md")),
        ("PRODUCT KNOWLEDGE",        _w("context/product_knowledge.md")),
        ("PRODUCT GUIDE",            _product_guide),          # CDP Layer 2: master guide
        ("INTERFACE MAP",            _w("context/interface_map.md")),
        ("TICKET TEMPLATE",          _w("context/ticket_template.md")),
        ("ENTITY RELATIONSHIPS",     _w("context/relationships.md")),
        ("ARCH DECISIONS",           _w("context/decisiones_arquitectura.md")),
        ("PRD INDEX",                _w("context/decisiones_prd.md")),
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("ANTI-PATTERNS",            _w("context/.reasoning_bank/anti_patrones.md")),
        ("HISTORICAL CONTEXT",       _w("context/Contexto_Historico_Proyecto.md")),
        ("AGENT DEFINITION",         _a("04_Desarrollador_Concepto/04_Desarrollador_Concepto.md")),
        ("SKILL: LOGICAL ARCH",      _a("04_Desarrollador_Concepto/Skills/01_Skill_Arquitectura_Logica.md")),
        ("SKILL: EDGE CASES",        _a("04_Desarrollador_Concepto/Skills/02_Skill_Anticipacion_Edge_Cases.md")),
        # CDP Layer 1 is injected dynamically via build_system_prompt(module=...)
    ],

    "escritor": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("SPRINT CONTEXT",           _w("context/sprint_context.md")),
        ("PRODUCT KNOWLEDGE",        _w("context/product_knowledge.md")),
        ("PRODUCT GUIDE",            _product_guide),          # CDP Layer 2: master guide
        ("INTERFACE MAP",            _w("context/interface_map.md")),
        ("TICKET TEMPLATE",          _w("context/ticket_template.md")),
        ("ENTITY RELATIONSHIPS",     _w("context/relationships.md")),
        ("HUMAN FEEDBACK",           _recent_feedback),         # last N entries only
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("ANTI-PATTERNS",            _w("context/.reasoning_bank/anti_patrones.md")),
        ("PRD INDEX",                _w("context/decisiones_prd.md")),
        ("AGENT DEFINITION",         _a("05_Escritor_USs/05_Escritor_USs.md")),
        ("SKILL: JIRA FORMAT",       _a("05_Escritor_USs/Skills/01_Skill_Traduccion_Jira_Markup.md")),
        ("SKILL: BDD",               _a("05_Escritor_USs/Skills/02_Skill_Estructuracion_BDD.md")),
        ("SKILL: DESIGN TASKS",      _a("05_Escritor_USs/Skills/03_Skill_Design_Tasks.md")),
        # CDP Layer 1 is injected dynamically via build_system_prompt(module=...)
    ],

    "qa": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("ANTI-PATTERNS",            _w("context/.reasoning_bank/anti_patrones.md")),
        ("AGENT DEFINITION",         _a("06_QA/06_QA.md")),
        ("SKILL: TECHNICAL TESTS",   _a("06_QA/Skills/01_Skill_Pruebas_Tecnicas.md")),
        ("SKILL: ROLE VALIDATION",   _a("06_QA/Skills/02_Skill_Validacion_Roles_QA.md")),
        # CDP Layer 1 is injected dynamically via build_system_prompt(module=...)
    ],

    "feedback": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("SUCCESSFUL PATTERNS",      _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("ANTI-PATTERNS",            _w("context/.reasoning_bank/anti_patrones.md")),
        ("AGENT DEFINITION",         _a("07_Feedback/07_Feedback.md")),
        ("SKILL: CONSTRUCTIVE CRITIC",_a("07_Feedback/Skills/01_Skill_Destruccion_Constructiva.md")),
        ("SKILL: ANTI-LOOP",         _a("07_Feedback/Skills/02_Skill_Anti_Loop_Terminator.md")),
        # CDP Layer 1 is injected dynamically via build_system_prompt(module=...)
    ],

    "meta_observador": [
        ("AGENT DEFINITION",         _a("08_Agente_Meta_Observador/08_Agente_Meta_Observador.md")),
        ("SKILL: METACOGNITIVE LOG",  _a("08_Agente_Meta_Observador/Skills/01_Skill_Registro_Metacognitivo.md")),
        ("SKILL: OPTIMIZATION MAP",  _a("08_Agente_Meta_Observador/Skills/02_Skill_Mapeo_Optimizacion.md")),
        ("SKILL: TRAJECTORIES",      _a("08_Agente_Meta_Observador/Skills/03_Skill_Trayectorias.md")),
        ("SKILL: MEMORY EXTRACTION", _a("08_Agente_Meta_Observador/Skills/04_Skill_Extraccion_Memoria.md")),
        ("EXISTING PATTERNS",        _w("context/.reasoning_bank/patrones_exitosos.md")),
        ("EXISTING ANTI-PATTERNS",   _w("context/.reasoning_bank/anti_patrones.md")),
        ("CURRENT PRODUCT KNOWLEDGE",_w("context/product_knowledge.md")),
        ("ENTITY RELATIONSHIPS",     _w("context/relationships.md")),
        ("SPRINT CONTEXT",           _w("context/sprint_context.md")),
        ("UNIVERSAL RULES",          _w("context/global.md")),
        # CDP Layer 1 (CURRENT MODULE CONTEXT) injected dynamically via build_system_prompt(module=...)
    ],

    # Agente standalone — usado por map_interface.py, no por el pipeline principal
    "mapeador": [
        ("UNIVERSAL RULES",          _w("context/global.md")),
        ("CURRENT INTERFACE MAP",    _w("context/interface_map.md")),
        ("AGENT DEFINITION",         _a("09_Mapeador_Interfaz/09_Mapeador_Interfaz.md")),
        ("SKILL: NAVEGACIÓN FRACTAL",_a("09_Mapeador_Interfaz/Skills/01_Skill_Navegacion_Fractal_Mapa.md")),
    ],
}


# ─── Main builder ─────────────────────────────────────────────────────────────

def build_system_prompt(
    agent_name:    str,
    module:        Optional[str] = None,
    extra_context: Optional[str] = None,
) -> str:
    """
    Build the system prompt for an agent using the Context Discovery Protocol.

    Args:
        agent_name:    key in AGENT_CONTEXT (e.g. "escritor")
        module:        target module name (e.g. "Billing", "Feature Flags")
                       If provided, injects module-specific context as Layer 1.
        extra_context: any additional context to append at the end

    Returns:
        Complete system prompt string for this agent.

    CDP behavior:
        - Missing context files are silently skipped (graceful degradation).
        - Module context is injected first if the module is known and has a
          context.md file in workspace/modules/.
        - First-time modules (no context.md yet) get a note that assumptions
          will be captured by the Meta-Observer after this run.
    """
    if agent_name not in AGENT_CONTEXT:
        raise ValueError(
            f"Unknown agent: '{agent_name}'. "
            f"Available: {list(AGENT_CONTEXT.keys())}"
        )

    parts: list[str] = [
        f"# AGENT CONTEXT: {agent_name.upper()}\n"
        f"You have access ONLY to the information provided here. "
        f"Do not assume anything not present in this document.\n"
    ]

    # ── CDP Layer 1: Module-specific context (injected first for max influence) ─
    if module:
        module_ctx = _module_context(module)
        if module_ctx:
            parts.append(_section(
                f"MODULE CONTEXT — {module.upper()} (CDP Layer 1)",
                module_ctx
            ))
        else:
            # First time for this module — document the gap
            parts.append(_section(
                f"MODULE CONTEXT — {module.upper()} (CDP Layer 1)",
                f"No prior context found for module '{module}'.\n"
                f"This appears to be the first ticket for this module.\n"
                f"Proceed using product knowledge and universal rules as baseline.\n"
                f"Document your assumptions clearly — the Meta-Observer will capture\n"
                f"them to build context.md for future runs."
            ))

    # ── CDP Layers 2-6: Standard agent context ─────────────────────────────────
    for section_name, resolver_fn in AGENT_CONTEXT[agent_name]:
        content = resolver_fn()
        if content:
            parts.append(_section(section_name, content))

    # ── Extra context (runtime injections: ticket history, linked issues, etc.) ─
    if extra_context:
        parts.append(_section("ADDITIONAL CONTEXT", extra_context))

    return "".join(parts)
