"""
application/bootstrap_service.py — Jira historical bootstrap for the desktop API.

Fetches completed tickets from Jira and uses AI to generate two context files:
  1. workspace/context/Contexto_Historico_Proyecto.md  — modules, team, epics, conventions
  2. workspace/context/.reasoning_bank/patrones_exitosos.md — writing style patterns

This is the API-friendly version of setup_wizard._bootstrap_historico_from_jira(),
extended with writing-style extraction (description sampling) and structured error reporting.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

import config
from utils.jira_client import _adf_to_text


# ── Error taxonomy ────────────────────────────────────────────────────────────

class BootstrapError(Exception):
    """Structured bootstrap error with a user-facing hint."""
    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_env() -> dict[str, str]:
    env: dict[str, str] = {}
    if config.ENV_FILE.exists():
        for line in config.ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _jira_auth_header(email: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def _jira_get(url: str, auth: str) -> dict:
    req = urllib.request.Request(url, headers={
        "Authorization": auth,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("errorMessages", [body[:200]])[0]
        except Exception:
            detail = body[:200]
        if e.code == 401:
            raise BootstrapError(
                "Autenticación fallida (401)",
                hint="El token de Jira es inválido o expiró. Genera uno nuevo en "
                     "https://id.atlassian.com/manage-profile/security/api-tokens "
                     "y actualízalo en Ajustes.",
            )
        if e.code == 403:
            raise BootstrapError(
                "Sin permiso para acceder a Jira (403)",
                hint="Verifica que tu cuenta tenga acceso de lectura al proyecto "
                     f"y que el token incluya el scope 'read:jira-work'.",
            )
        if e.code == 404:
            raise BootstrapError(
                f"Recurso no encontrado en Jira (404): {detail}",
                hint="Verifica que JIRA_BASE_URL sea correcto "
                     "(ejemplo: https://tuempresa.atlassian.net).",
            )
        raise BootstrapError(f"Error Jira {e.code}: {detail}")
    except urllib.error.URLError as e:
        reason = str(e.reason)
        if "CERTIFICATE_VERIFY_FAILED" in reason or "Hostname mismatch" in reason:
            raise BootstrapError(
                "No se puede conectar a Jira — URL inválida",
                hint="La URL configurada parece ser un placeholder. "
                     "Usa el formato: https://tuempresa.atlassian.net",
            )
        raise BootstrapError(
            f"Error de red: {reason}",
            hint="Verifica tu conexión a internet y que JIRA_BASE_URL sea accesible.",
        )


def _call_ai(prompt: str, provider: str, model: str, env: dict[str, str]) -> str:
    """Call the configured AI provider. Returns the text response."""
    if provider == "anthropic":
        key = env.get("ANTHROPIC_API_KEY", "")
        if not key or len(key) < 20:
            raise BootstrapError(
                "ANTHROPIC_API_KEY no configurada",
                hint="Agrega tu API key de Anthropic en Ajustes.",
            )
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            resp = client.messages.create(
                model=model, max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            raise BootstrapError(f"Error de IA (Anthropic): {e}",
                                 hint="Verifica que tu API key de Anthropic sea válida.")

    elif provider == "openai":
        key = env.get("OPENAI_API_KEY", "")
        if not key or len(key) < 20:
            raise BootstrapError(
                "OPENAI_API_KEY no configurada",
                hint="Agrega tu API key de OpenAI en Ajustes.",
            )
        try:
            payload = json.dumps({
                "model": model, "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=payload,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            choices = body.get("choices") or []
            if not choices:
                raise BootstrapError("OpenAI devolvió una respuesta vacía.")
            return choices[0]["message"]["content"]
        except BootstrapError:
            raise
        except Exception as e:
            raise BootstrapError(f"Error de IA (OpenAI): {e}",
                                 hint="Verifica que tu API key de OpenAI sea válida.")

    elif provider == "google":
        key = env.get("GOOGLE_API_KEY", "")
        if not key or len(key) < 20:
            raise BootstrapError(
                "GOOGLE_API_KEY no configurada",
                hint="Agrega tu API key de Google en Ajustes.",
            )
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"/{model}:generateContent?key={key}"
            )
            payload = json.dumps({
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.3},
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
            return body["candidates"][0]["content"]["parts"][0]["text"]
        except BootstrapError:
            raise
        except Exception as e:
            raise BootstrapError(f"Error de IA (Google): {e}",
                                 hint="Verifica que tu API key de Google sea válida.")

    raise BootstrapError(
        f"Proveedor desconocido: {provider!r}",
        hint="Configura PROVIDER como 'anthropic', 'openai' o 'google' en Ajustes.",
    )


# ── Main bootstrap ─────────────────────────────────────────────────────────────

def run_bootstrap() -> dict[str, Any]:
    """
    Fetch Jira history and generate context files.

    Returns a structured result dict:
      {
        "ok": bool,
        "tickets_fetched": int,
        "style_samples": int,        # tickets used for writing style analysis
        "files_updated": list[str],  # filenames written
        "summary": str,              # one-paragraph human-readable summary
        "error": str,                # only on failure
        "hint": str,                 # remediation hint on failure
      }
    """
    env = _read_env()

    base_url  = env.get("JIRA_BASE_URL", "").strip()
    email     = env.get("JIRA_EMAIL", "").strip()
    token     = env.get("JIRA_API_TOKEN", "").strip()
    proj_key  = env.get("JIRA_PROJECT_KEY", "").strip()
    provider  = env.get("PROVIDER", "google").lower()
    model     = env.get("DEFAULT_MODEL", "gemini-2.5-flash-lite")

    # ── Validate config ────────────────────────────────────────────────────────
    _PLACEHOLDERS = {"TU_EMPRESA", "TU_EMAIL", "your-company", "your@email", ""}
    if not base_url or any(p in base_url for p in _PLACEHOLDERS):
        return _err(
            "JIRA_BASE_URL no configurada",
            "Completa la URL base de Jira en Ajustes (ejemplo: https://tuempresa.atlassian.net).",
        )
    if not email or any(p in email for p in _PLACEHOLDERS):
        return _err(
            "JIRA_EMAIL no configurado",
            "Completa tu email de Jira en Ajustes.",
        )
    if not token:
        return _err(
            "JIRA_API_TOKEN no configurado",
            "Genera un token en https://id.atlassian.com/manage-profile/security/api-tokens "
            "y guárdalo en Ajustes.",
        )

    auth = _jira_auth_header(email, token)

    # ── Fetch completed tickets (summary-level, up to 200) ─────────────────────
    try:
        six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
        done = "Done, Finalizada, Cerrada, Released, 'To Be Released', Closed, Completed"
        jql = (
            f"project = {proj_key} AND status in ({done}) AND created >= '{six_months_ago}' "
            f"ORDER BY created DESC"
        ) if proj_key else (
            f"status in ({done}) AND created >= '{six_months_ago}' ORDER BY created DESC"
        )

        search_url = (
            f"{base_url.rstrip('/')}/rest/api/3/search/jql"
            f"?jql={urllib.parse.quote(jql)}&maxResults=200"
            f"&fields=summary,issuetype,assignee,status,created,description"
        )
        data = _jira_get(search_url, auth)
    except BootstrapError:
        raise
    except Exception as e:
        raise BootstrapError(str(e))

    issues = data.get("issues", [])
    if not issues:
        return _err(
            f"No se encontraron tickets completados en los últimos 6 meses "
            f"{'en el proyecto ' + proj_key if proj_key else ''}.",
            "Verifica que el proyecto tenga tickets en estado Done/Cerrada/Completed, "
            "o ajusta JIRA_PROJECT_KEY en Ajustes.",
        )

    n = len(issues)

    # ── Build compact ticket list for context analysis ─────────────────────────
    rows: list[str] = []
    for issue in issues[:150]:
        f = issue.get("fields", {})
        key     = issue.get("key", "?")
        itype   = f.get("issuetype", {}).get("name", "?")
        assignee = (f.get("assignee") or {}).get("displayName", "Unassigned")
        status  = f.get("status", {}).get("name", "?")
        summary = f.get("summary", "")
        rows.append(f"[{key}][{itype}][{status}][{assignee}]: {summary}")
    tickets_block = "\n".join(rows)

    # ── Collect writing samples (top 25 tickets with non-empty descriptions) ───
    samples: list[str] = []
    for issue in issues:
        if len(samples) >= 25:
            break
        f = issue.get("fields", {})
        desc_raw = f.get("description")
        if not desc_raw:
            continue
        desc = _adf_to_text(desc_raw).strip()
        if len(desc) < 100:
            continue
        key     = issue.get("key", "?")
        itype   = f.get("issuetype", {}).get("name", "?")
        summary = f.get("summary", "")
        samples.append(f"--- {key} [{itype}]: {summary} ---\n{desc[:1500]}")

    style_count = len(samples)
    samples_block = "\n\n".join(samples) if samples else "(No se encontraron descripciones con contenido suficiente)"

    # ── AI call 1: Historical context ─────────────────────────────────────────
    context_prompt = f"""Analyze {n} completed tickets from a software product team.

TICKETS (key, type, status, assignee, summary):
{tickets_block}

Generate a structured Markdown document in Spanish with these sections:

## Equipo y Roles
List each person found in assignee data: name, ticket count, inferred role.

## Módulos del Producto
Group tickets into feature areas. For each: name, ticket count, one-line description.

## Épicas Completadas
Major initiatives clearly finished (majority Done/Closed).

## Épicas Activas
Themes still being worked on.

## Convenciones Observadas
3–5 patterns in how this team names and structures tickets.

## Plataforma y Dominio
Any platform rules implied (Web/Mobile/Desktop, out-of-scope areas).

Rules: ONLY extract what is clearly visible in the data. Do not invent. Be concise — this is read by AI agents, not humans.
Responde en español."""

    context_text = _call_ai(context_prompt, provider, model, env)

    # ── AI call 2: Writing style ───────────────────────────────────────────────
    style_prompt = f"""Analyze these {style_count} real tickets from a software team to extract their writing style.

{samples_block}

Generate a Markdown document in Spanish with these sections:

## Estructura de Ticket Típica
Show the skeleton/outline structure this team uses (headers, sections, order).

## Estilo de Escritura
- Tone (formal/informal, imperative/declarative)
- Language(s) used (Spanish/English/bilingual)
- Level of technical detail
- Acceptance criteria format (Gherkin/bullets/prose)

## Patrones de Criterios de Aceptación
3–5 examples of how they write AC, with the observable pattern labeled.

## Patrones de Nomenclatura
How they title tickets (verb+noun, imperative, descriptive, etc.)

## Qué Evitar
Anti-patterns or inconsistencies seen in the tickets.

Rules: Extract ONLY from the examples provided. Use direct, actionable language — this document will be read by an AI writing agent before generating every ticket.
Responde en español."""

    style_text = _call_ai(style_prompt, provider, model, env)

    # ── Write output files ─────────────────────────────────────────────────────
    today = datetime.now().strftime("%Y-%m-%d")
    files_updated: list[str] = []

    context_dir = config.WORKSPACE_DIR / "context"
    context_dir.mkdir(parents=True, exist_ok=True)

    reasoning_dir = context_dir / ".reasoning_bank"
    reasoning_dir.mkdir(parents=True, exist_ok=True)

    # File 1: Contexto_Historico_Proyecto.md
    historico_path = context_dir / "Contexto_Historico_Proyecto.md"
    historico_path.write_text(
        f"# CONTEXTO HISTÓRICO DEL PROYECTO\n"
        f"## Generado: {today} | Fuente: Bootstrap de Jira ({n} tickets, últimos 6 meses)\n"
        f"## Auto-enriquecido por: Meta-Observador tras cada ticket aprobado\n\n"
        f"> Generado automáticamente. Edita libremente para corregir o completar.\n"
        f"> El Meta-Observador AÑADE información tras cada corrida — nunca reemplaza.\n\n"
        f"---\n\n"
        f"{context_text}\n",
        encoding="utf-8",
    )
    files_updated.append("Contexto_Historico_Proyecto.md")

    # File 2: patrones_exitosos.md
    patrones_path = reasoning_dir / "patrones_exitosos.md"
    patrones_path.write_text(
        f"# PATRONES EXITOSOS — ESTILO DE ESCRITURA\n"
        f"## Generado: {today} | Fuente: {style_count} tickets de Jira con descripción completa\n"
        f"## Leído por: Escritor_USs antes de generar cada ticket\n\n"
        f"> Estos patrones reflejan el estilo real del equipo.\n"
        f"> El Meta-Observador los enriquece con cada ticket aprobado.\n\n"
        f"---\n\n"
        f"{style_text}\n",
        encoding="utf-8",
    )
    files_updated.append(".reasoning_bank/patrones_exitosos.md")

    summary = (
        f"Se extrajeron {n} tickets completados de los últimos 6 meses"
        f"{' del proyecto ' + proj_key if proj_key else ''}. "
        f"Se analizaron {style_count} tickets con descripción completa para aprender el estilo de escritura del equipo. "
        f"Se generaron 2 archivos de contexto: historial del proyecto (módulos, equipo, épicas) "
        f"y patrones de escritura (estructura, criterios de aceptación, nomenclatura). "
        f"El pipeline usará este contexto desde el próximo ticket."
    )

    return {
        "ok": True,
        "tickets_fetched": n,
        "style_samples": style_count,
        "files_updated": files_updated,
        "summary": summary,
    }


def _err(message: str, hint: str = "") -> dict[str, Any]:
    return {
        "ok": False,
        "tickets_fetched": 0,
        "style_samples": 0,
        "files_updated": [],
        "summary": "",
        "error": message,
        "hint": hint,
    }
