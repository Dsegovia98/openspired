"""
config.py — Configuración central del pipeline.
Soporta múltiples proveedores: anthropic | openai | google
Estructura: <PROJECT_ROOT>/engine/config.py
"""
from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Workspace mode detection ─────────────────────────────────────────────────
#
# External workspace mode: set WORKSPACE_PATH env var before running.
# Openspired will load .env from the workspace's parent directory and use
# that workspace for all context files (global.md, sprint_context.md, etc.).
#
# Example (run.sh in an external project):
#   export WORKSPACE_PATH="/path/to/my-project/workspace"
#   export AGENTS_PATH="/path/to/my-project/agents"   # optional
#   python /path/to/openspired/engine/run.py
#
_workspace_path_env = os.getenv("WORKSPACE_PATH", "")

# .env vive en la raíz del proyecto, o junto al workspace externo
if _workspace_path_env:
    _ENV_FILE = Path(_workspace_path_env).parent / ".env"
else:
    _ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE, override=True)


def _find_project_root() -> Path:
    # engine/ vive en: <PROJECT_ROOT>/engine/
    # Raíz = 1 nivel arriba del directorio de este archivo.
    return Path(__file__).resolve().parent.parent


# ─── Rutas ────────────────────────────────────────────────────────────────────
PROJECT_ROOT:  Path = _find_project_root()
ENGINE_DIR:    Path = Path(__file__).parent
WORKSPACE_DIR: Path = Path(_workspace_path_env) if _workspace_path_env else PROJECT_ROOT / "workspace"
AGENTS_DIR:    Path = Path(os.getenv("AGENTS_PATH", str(PROJECT_ROOT / "agents")))
LOGS_DIR:      Path = WORKSPACE_DIR / "logs"
RUNS_DIR:      Path = LOGS_DIR / "pipeline_runs"

# ─── Proveedor y modelos ───────────────────────────────────────────────────────
#
# PROVIDER controla cuál API usar por defecto.
# DEFAULT_MODEL es el modelo para todos los agentes (a menos que tengan override).
# USE_CACHE activa el prompt caching de Anthropic (90% descuento en input repetido).
#
PROVIDER:      str  = os.getenv("PROVIDER", "anthropic").lower()
DEFAULT_MODEL: str  = os.getenv("DEFAULT_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS:    int  = int(os.getenv("MAX_TOKENS", "8192"))
USE_CACHE:     bool = os.getenv("USE_CACHE", "true").lower() == "true"
MAX_REVISIONS: int  = int(os.getenv("MAX_REVISIONS", "2"))

# ─── API Keys ─────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY:    str = os.getenv("OPENAI_API_KEY",    "")
GOOGLE_API_KEY:    str = os.getenv("GOOGLE_API_KEY",    "")

# ─── Modelo por agente (opcional — override del DEFAULT_MODEL) ────────────────
#
# Si no se especifica, todos usan DEFAULT_MODEL.
# Útil para poner Sonnet solo en los agentes que más importan.
#
AGENT_MODELS: dict[str, str] = {
    "orquestador":    os.getenv("MODEL_ORQUESTADOR",    DEFAULT_MODEL),
    "ideador":        os.getenv("MODEL_IDEADOR",        DEFAULT_MODEL),
    "researcher":     os.getenv("MODEL_RESEARCHER",     DEFAULT_MODEL),
    "dev_concepto":   os.getenv("MODEL_DEV_CONCEPTO",   DEFAULT_MODEL),
    "escritor":       os.getenv("MODEL_ESCRITOR",       DEFAULT_MODEL),
    "qa":             os.getenv("MODEL_QA",             DEFAULT_MODEL),
    "feedback":       os.getenv("MODEL_FEEDBACK",       DEFAULT_MODEL),
    "documentador":   os.getenv("MODEL_DOCUMENTADOR",   DEFAULT_MODEL),
    "meta_observador":os.getenv("MODEL_META_OBSERVADOR",DEFAULT_MODEL),
}

# Backward compat: ANTHROPIC_MODEL sigue siendo válido si PROVIDER=anthropic
_legacy = os.getenv("ANTHROPIC_MODEL", "")
if _legacy and PROVIDER == "anthropic" and DEFAULT_MODEL == "claude-haiku-4-5-20251001":
    DEFAULT_MODEL = _legacy

# ─── Validación ───────────────────────────────────────────────────────────────
_KEY_MAP = {
    "anthropic": ANTHROPIC_API_KEY,
    "openai":    OPENAI_API_KEY,
    "google":    GOOGLE_API_KEY,
}
if not _KEY_MAP.get(PROVIDER):
    _key_var = {"anthropic": "ANTHROPIC_API_KEY",
                "openai":    "OPENAI_API_KEY",
                "google":    "GOOGLE_API_KEY"}.get(PROVIDER, "API_KEY")
    raise EnvironmentError(
        f"Proveedor '{PROVIDER}' seleccionado pero {_key_var} no está configurada.\n"
        f"Edita {_ENV_FILE} y agrega tu API key."
    )

RUNS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Integración Jira (opcional) ──────────────────────────────────────────────
#
# Solo se requiere cuando usas: python3 run.py --jira CAKE-123
# Si no tienes configuración de Jira, el pipeline funciona igual sin ella.
#
JIRA_BASE_URL:    str = os.getenv("JIRA_BASE_URL",    "")   # https://tuempresa.atlassian.net
JIRA_EMAIL:       str = os.getenv("JIRA_EMAIL",       "")   # tu@email.com
JIRA_API_TOKEN:   str = os.getenv("JIRA_API_TOKEN",   "")   # token de Atlassian
JIRA_PROJECT_KEY:           str = os.getenv("JIRA_PROJECT_KEY",           "")   # ej: MYAPP
JIRA_PROJECT_KEY_SECONDARY: str = os.getenv("JIRA_PROJECT_KEY_SECONDARY", "ANA")  # 2nd domain

# ─── Domain config ─────────────────────────────────────────────────────────────
#
# DOMAIN_PRIMARY  : the main product domain (used by Orchestrator to classify tickets)
# DOMAIN_SECONDARY: the secondary domain (analytics, data, etc.)
# These are set by the setup wizard and saved to .env. Override manually if needed.
#
DOMAIN_PRIMARY:   str = os.getenv("DOMAIN_PRIMARY",   "App")
DOMAIN_SECONDARY: str = os.getenv("DOMAIN_SECONDARY", "Analytics")

_JIRA_PLACEHOLDERS = {"TU_EMPRESA", "TU_EMAIL", "TU_JIRA_API_TOKEN_AQUI", "TU_"}
def _is_placeholder(v: str) -> bool:
    return any(p in v for p in _JIRA_PLACEHOLDERS)

JIRA_ENABLED: bool = bool(
    JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN
    and not _is_placeholder(JIRA_BASE_URL)
    and not _is_placeholder(JIRA_EMAIL)
    and not _is_placeholder(JIRA_API_TOKEN)
)

# ─── Compatibilidad legacy ────────────────────────────────────────────────────
MODEL = DEFAULT_MODEL  # algunos módulos viejos leen MODEL directamente
