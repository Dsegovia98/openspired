"""
utils/jira_client.py — Cliente Jira REST API para el pipeline.

Usa urllib puro (sin dependencias externas).
Soporta Jira Cloud (atlassian.net).

Lectura:  API v3 (devuelve ADF → se convierte a texto plano)
Escritura: API v2 (acepta Jira wiki markup → compatible con output del Escritor)
"""
from __future__ import annotations
import base64
import json
import re
import urllib.error
import urllib.request
from typing import Optional


class JiraClient:
    """Wrapper minimalista sobre la Jira REST API."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self._base = base_url.rstrip("/")
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth = f"Basic {token}"

    # ─── Lectura ──────────────────────────────────────────────────────────────

    def get_issue(self, issue_key: str) -> dict:
        """
        Lee un issue de Jira y retorna un dict con todo el contexto relevante:
          key, summary, description, issue_type, pipeline_type, project_key,
          status, linked_issues, labels, components, epic_key, epic_summary,
          parent_key, parent_summary, recent_comments (últimos 5)
        """
        issue_key = _normalize_key(issue_key)
        # Fetch main fields including labels, components, parent, epic link
        fields_param = (
            "summary,description,issuetype,project,status,issuelinks,"
            "labels,components,parent,priority,"
            "customfield_10014"  # epic link (classic Jira)
        )
        data = self._request(
            "GET", f"issue/{issue_key}?fields={fields_param}", api_version=3
        )
        fields = data["fields"]

        raw_type = fields["issuetype"]["name"]

        # Labels and components — useful for module classification
        labels = [lb for lb in (fields.get("labels") or []) if lb]
        components = [c.get("name", "") for c in (fields.get("components") or [])]

        # Parent issue (subtask → parent Story, Story → Epic)
        parent_key = parent_summary = ""
        parent = fields.get("parent")
        if parent:
            parent_key    = parent.get("key", "")
            parent_fields = parent.get("fields", {})
            parent_summary = parent_fields.get("summary", "")

        # Epic link (classic projects use customfield_10014)
        epic_key = epic_summary = ""
        epic_link = fields.get("customfield_10014") or ""
        if epic_link and re.match(r"[A-Z][A-Z0-9]+-\d+", str(epic_link)):
            epic_key = str(epic_link)
            try:
                epic_data = self._request(
                    "GET", f"issue/{epic_key}?fields=summary", api_version=3
                )
                epic_summary = epic_data["fields"].get("summary", "")
            except Exception:
                pass  # Epic fetch failure is non-critical

        # Fetch recent comments (up to 5, most recent first)
        recent_comments: list[dict] = []
        try:
            comments_data = self._request(
                "GET",
                f"issue/{issue_key}/comment?maxResults=5&orderBy=-created",
                api_version=3,
            )
            for c in (comments_data.get("comments") or [])[:5]:
                author = (c.get("author") or {}).get("displayName", "Unknown")
                body   = _adf_to_text(c.get("body"))
                if body and body.strip():
                    recent_comments.append({"author": author, "body": body.strip()})
        except Exception:
            pass  # Comments fetch failure is non-critical

        pipeline_type = _map_issue_type(raw_type)
        # Warn when the issue type is remapped to a different pipeline type.
        # This prevents silent treatment of bugs/epics as user stories.
        type_warning = ""
        _NATIVE_TYPES = {"story", "user story", "historia", "design task", "design"}
        if raw_type.lower().strip() not in _NATIVE_TYPES:
            type_warning = (
                f"⚠️  Tipo '{raw_type}' no es nativo del pipeline — "
                f"se procesará como '{pipeline_type}'. "
                f"Verifica que el resultado sea el esperado."
            )

        return {
            "key":             data["key"],
            "summary":         fields.get("summary", "Sin título"),
            "description":     _adf_to_text(fields.get("description")),
            "issue_type":      raw_type,
            "pipeline_type":   pipeline_type,
            "type_warning":    type_warning,
            "project_key":     fields["project"]["key"],
            "status":          fields["status"]["name"],
            "linked_issues":   self._enrich_linked_issues(
                                   _extract_links(fields.get("issuelinks", [])),
                                   max_descriptions=5,
                               ),
            "labels":          labels,
            "components":      components,
            "parent_key":      parent_key,
            "parent_summary":  parent_summary,
            "epic_key":        epic_key,
            "epic_summary":    epic_summary,
            "recent_comments": recent_comments,
        }

    # ─── Escritura ────────────────────────────────────────────────────────────

    def update_description(self, issue_key: str, wiki_content: str) -> None:
        """
        Reemplaza la descripción del issue con contenido en Jira Wiki Markup.
        Usa API v2 que acepta strings (no ADF).
        """
        issue_key = _normalize_key(issue_key)
        self._request(
            "PUT",
            f"issue/{issue_key}",
            payload={"fields": {"description": wiki_content}},
            api_version=2,
        )

    def add_comment(self, issue_key: str, wiki_content: str) -> str:
        """
        Agrega un comentario al issue. Retorna el ID del comentario creado.
        """
        issue_key = _normalize_key(issue_key)
        result = self._request(
            "POST",
            f"issue/{issue_key}/comment",
            payload={"body": wiki_content},
            api_version=2,
        )
        return result.get("id", "")

    def _enrich_linked_issues(
        self,
        linked: list[dict],
        max_descriptions: int = 5,
    ) -> list[dict]:
        """
        Fetches the full description for each linked issue (up to max_descriptions).

        Prioritizes issues with richer types (Design Tasks, Stories) and caps
        the total to avoid too many API round-trips. Failures are silently
        skipped — enrichment is best-effort.

        Each result dict gains a "description" key (plain text, may be empty).
        """
        enriched = []
        fetched = 0
        for lnk in linked:
            if fetched >= max_descriptions:
                # For issues beyond the cap, add without description
                lnk.setdefault("description", "")
                enriched.append(lnk)
                continue
            try:
                data = self._request(
                    "GET",
                    f"issue/{lnk['key']}?fields=description,issuetype,summary",
                    api_version=3,
                )
                desc = _adf_to_text(data["fields"].get("description"))
                lnk["description"] = desc.strip() if desc else ""
                fetched += 1
            except Exception:
                lnk["description"] = ""
            enriched.append(lnk)
        return enriched

    def get_epic_children(self, epic_key: str, max_results: int = 8) -> list[dict]:
        """
        Retorna los issues hijos (siblings) de una épica.

        Prueba dos estrategias en orden:
          1. JQL: issue in childIssuesOf("{epic_key}")  — funciona en Jira moderno (NextGen)
          2. JQL: "Epic Link" = "{epic_key}"            — funciona en proyectos clásicos

        Cada resultado incluye: key, summary, status, issue_type.
        Errores de red o JQL inválido se silencian — el contexto es best-effort.
        """
        epic_key = _normalize_key(epic_key)
        strategies = [
            f'issue in childIssuesOf("{epic_key}")',
            f'"Epic Link" = "{epic_key}"',
        ]
        fields = "summary,status,issuetype"
        for jql in strategies:
            try:
                import urllib.parse
                path = f"search?jql={urllib.parse.quote(jql)}&fields={fields}&maxResults={max_results}"
                data = self._request("GET", path, api_version=3)
                issues = data.get("issues", [])
                if issues:
                    return [
                        {
                            "key":        i["key"],
                            "summary":    i["fields"].get("summary", ""),
                            "status":     i["fields"].get("status", {}).get("name", ""),
                            "issue_type": i["fields"].get("issuetype", {}).get("name", ""),
                        }
                        for i in issues
                    ]
            except Exception:
                continue
        return []

    def get_sprint_goal(self, project_key: str) -> dict:
        """
        Busca el sprint activo del proyecto y retorna su nombre y objetivo.

        Usa la Jira Agile API (/rest/agile/1.0/).
        Retorna {"name": ..., "goal": ...} o {} si no se puede obtener.

        Nota: requiere permisos de lectura de boards (scope: read:jira-work).
        """
        try:
            import urllib.parse
            # Buscar boards del proyecto
            path = f"board?projectKeyOrId={urllib.parse.quote(project_key)}&maxResults=5"
            boards_data = self._request("GET", path, api_base="rest/agile", api_version="1.0")
            boards = boards_data.get("values", [])
            if not boards:
                return {}

            # Usar el primer board encontrado (normalmente el Scrum board)
            board_id = boards[0]["id"]

            # Buscar sprint activo en ese board
            sprint_path = f"board/{board_id}/sprint?state=active&maxResults=1"
            sprints_data = self._request("GET", sprint_path, api_base="rest/agile", api_version="1.0")
            sprints = sprints_data.get("values", [])
            if not sprints:
                return {}

            sprint = sprints[0]
            return {
                "name": sprint.get("name", ""),
                "goal": sprint.get("goal", ""),
            }
        except Exception:
            return {}

    def get_project_issue_types(self, project_key: str) -> list[dict]:
        """Lista los tipos de issue disponibles en un proyecto."""
        data = self._request("GET", f"project/{project_key}", api_version=3)
        return [
            {"id": it["id"], "name": it["name"]}
            for it in data.get("issueTypes", [])
        ]

    # ─── HTTP ─────────────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[dict] = None,
        api_version: "int | str" = 3,
        api_base: str = "rest/api",
    ) -> dict:
        url = f"{self._base}/{api_base}/{api_version}/{path}"
        data = json.dumps(payload).encode("utf-8") if payload else None

        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": self._auth,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            raise JiraAPIError(e.code, path, error_body) from e
        except urllib.error.URLError as e:
            reason = str(e.reason)
            if "CERTIFICATE_VERIFY_FAILED" in reason or "Hostname mismatch" in reason:
                raise RuntimeError(
                    "No se puede conectar a Jira: la URL configurada parece ser un placeholder.\n"
                    "   Edita el archivo .env y completa:\n"
                    "     JIRA_BASE_URL=https://TU-EMPRESA-REAL.atlassian.net\n"
                    "     JIRA_EMAIL=tu@email.com\n"
                    "     JIRA_API_TOKEN=<token de https://id.atlassian.com/manage-profile/security/api-tokens>"
                ) from e
            raise RuntimeError(f"Error de red al conectar con Jira: {e}") from e


# ─── Helpers ──────────────────────────────────────────────────────────────────

class JiraAPIError(RuntimeError):
    """Error de la API de Jira con contexto legible."""

    def __init__(self, status: int, path: str, body: str):
        self.status = status
        try:
            data = json.loads(body)
            messages = data.get("errorMessages", []) or [
                str(v) for v in (data.get("errors") or {}).values()
            ]
            detail = "; ".join(messages) or body[:200]
        except Exception:
            detail = body[:200]
        super().__init__(f"Jira API {status} en /{path}: {detail}")


def _normalize_key(key_or_url: str) -> str:
    """
    Acepta tanto 'CAKE-123' como
    'https://empresa.atlassian.net/browse/CAKE-123'
    y retorna solo la clave: 'CAKE-123'
    """
    key_or_url = key_or_url.strip()
    match = re.search(r"([A-Z][A-Z0-9]+-\d+)", key_or_url)
    if match:
        return match.group(1)
    raise ValueError(f"No se pudo extraer una clave de Jira de: '{key_or_url}'")


# Mapeo de nombres de tipo Jira → tipo que entiende el pipeline
_ISSUE_TYPE_MAP: dict[str, str] = {
    # User Stories
    "story":        "User Story",
    "historia":     "User Story",
    "user story":   "User Story",
    "feature":      "User Story",
    # Design Tasks
    "design task":  "Design Task",
    "design":       "Design Task",
    # Tasks genéricas — por defecto van como US
    "task":         "User Story",
    "tarea":        "User Story",
    "subtask":      "User Story",
    "sub-task":     "User Story",
    # Bugs / otros — tratarlos como US (el Orquestador puede refinar)
    "bug":          "User Story",
    "epic":         "User Story",
    "initiative":   "User Story",
}


def _map_issue_type(raw_type: str) -> str:
    """Mapea el tipo de issue de Jira al tipo que reconoce el pipeline."""
    return _ISSUE_TYPE_MAP.get(raw_type.lower().strip(), "User Story")


def _extract_links(issuelinks: list) -> list[dict]:
    """
    Extrae las incidencias vinculadas de la lista `issuelinks` de la API v3.

    Cada elemento del resultado tiene:
      - relation: texto legible del vínculo (e.g. 'blocks', 'is blocked by')
      - key:      clave del issue vinculado (e.g. 'CAKE-100')
      - summary:  título del issue vinculado
      - status:   estado del issue vinculado
      - type:     tipo de issue vinculado (e.g. 'Story', 'Task')
    """
    result = []
    for link in issuelinks:
        link_type = link.get("type", {})

        # El issue vinculado puede estar en inwardIssue o outwardIssue
        if "inwardIssue" in link:
            related = link["inwardIssue"]
            relation = link_type.get("inward", "relacionado con")
        elif "outwardIssue" in link:
            related = link["outwardIssue"]
            relation = link_type.get("outward", "relacionado con")
        else:
            continue

        related_fields = related.get("fields", {})
        result.append({
            "relation": relation,
            "key":      related["key"],
            "summary":  related_fields.get("summary", ""),
            "status":   related_fields.get("status", {}).get("name", ""),
            "type":     related_fields.get("issuetype", {}).get("name", ""),
        })

    return result


def _adf_to_text(node: Optional[dict | str], depth: int = 0) -> str:
    """
    Convierte un nodo ADF (Atlassian Document Format) a texto plano.
    Cubre todos los tipos relevantes: doc, paragraph, text, heading,
    bulletList, orderedList, listItem, hardBreak, rule, table, panel,
    expand, blockquote, codeBlock, mention, inlineCard, mediaSingle.
    """
    if not node:
        return ""
    if isinstance(node, str):
        return node

    node_type = node.get("type", "")
    content   = node.get("content", [])
    text_val  = node.get("text", "")
    attrs     = node.get("attrs", {})

    if node_type == "text":
        return text_val

    if node_type == "doc":
        return "\n\n".join(filter(None, [_adf_to_text(c, depth) for c in content]))

    if node_type == "paragraph":
        inner = "".join([_adf_to_text(c, depth) for c in content])
        return inner.strip()

    if node_type == "heading":
        level = attrs.get("level", 1)
        inner = "".join([_adf_to_text(c, depth) for c in content])
        return "#" * level + " " + inner.strip()

    if node_type == "bulletList":
        items = [_adf_to_text(c, depth + 1) for c in content]
        return "\n".join(f"{'  ' * depth}* {i}" for i in items if i)

    if node_type == "orderedList":
        items = [_adf_to_text(c, depth + 1) for c in content]
        return "\n".join(f"{'  ' * depth}{i+1}. {item}" for i, item in enumerate(items) if item)

    if node_type == "listItem":
        return "\n".join(filter(None, [_adf_to_text(c, depth) for c in content]))

    if node_type == "hardBreak":
        return "\n"

    if node_type == "rule":
        return "\n---\n"

    if node_type in ("strong", "em", "strike", "underline", "subsup"):
        return text_val or "".join([_adf_to_text(c, depth) for c in content])

    if node_type == "code":
        return f"`{text_val}`"

    if node_type == "link":
        href = attrs.get("href", "")
        inner = "".join([_adf_to_text(c, depth) for c in content]) or href
        return f"{inner} ({href})" if href and href != inner else inner

    if node_type == "codeBlock":
        lang = attrs.get("language", "")
        inner = "".join([_adf_to_text(c, depth) for c in content])
        return f"```{lang}\n{inner}\n```"

    if node_type == "blockquote":
        inner = "\n".join(filter(None, [_adf_to_text(c, depth) for c in content]))
        return "\n".join(f"> {line}" for line in inner.split("\n"))

    # ── Tables — critical: Jira AC is often in table cells ────────────────────
    if node_type == "table":
        rows = [_adf_to_text(c, depth) for c in content]
        return "\n".join(r for r in rows if r)

    if node_type == "tableRow":
        cells = [_adf_to_text(c, depth) for c in content]
        return "  |  ".join(c.strip().replace("\n", " ") for c in cells if c.strip())

    if node_type in ("tableCell", "tableHeader"):
        inner = " ".join(filter(None, [_adf_to_text(c, depth) for c in content]))
        return inner.strip()

    # ── Panel — info/warning/note boxes, often contain AC ─────────────────────
    if node_type == "panel":
        panel_type = attrs.get("panelType", "info").upper()
        inner = "\n".join(filter(None, [_adf_to_text(c, depth) for c in content]))
        return f"[{panel_type}]\n{inner}"

    # ── Expand — collapsible sections ─────────────────────────────────────────
    if node_type == "expand":
        title = attrs.get("title", "")
        inner = "\n".join(filter(None, [_adf_to_text(c, depth) for c in content]))
        return f"[{title}]\n{inner}" if title else inner

    # ── Mention — @user references ────────────────────────────────────────────
    if node_type == "mention":
        return f"@{attrs.get('text', attrs.get('id', ''))}"

    # ── Inline cards (Jira issue links embedded in text) ──────────────────────
    if node_type == "inlineCard":
        url = attrs.get("url", "")
        match = re.search(r"([A-Z][A-Z0-9]+-\d+)", url)
        return match.group(1) if match else url

    # ── Media (images/attachments) — just note their presence ─────────────────
    if node_type in ("mediaSingle", "media"):
        alt = attrs.get("alt", "")
        return f"[image: {alt}]" if alt else "[image]"

    # ── Emoji ─────────────────────────────────────────────────────────────────
    if node_type == "emoji":
        return attrs.get("text", attrs.get("shortName", ""))

    # Fallback: concatenate child content
    parts = [_adf_to_text(c, depth) for c in content]
    if text_val:
        parts.insert(0, text_val)
    return " ".join(filter(None, parts))
