from __future__ import annotations

from typing import Any, Callable

from config import JIRA_API_TOKEN, JIRA_BASE_URL, JIRA_EMAIL
from pipeline import run_pipeline
from utils.jira_client import JiraAPIError, JiraClient, _normalize_key


class JiraFlowError(RuntimeError):
    """Raised when Jira mode cannot continue."""


def build_po_input_from_issue(issue: dict[str, Any]) -> str:
    """Builds an enriched PO input from Jira issue payload."""
    labels = issue.get("labels", [])
    comps = issue.get("components", [])
    comments = issue.get("recent_comments", [])
    epic_k = issue.get("epic_key", "")
    epic_s = issue.get("epic_summary", "")
    par_k = issue.get("parent_key", "")
    par_s = issue.get("parent_summary", "")

    meta_lines = []
    if labels:
        meta_lines.append(f"Labels: {', '.join(labels)}")
    if comps:
        meta_lines.append(f"Componentes: {', '.join(comps)}")
    if epic_k:
        meta_lines.append(f"Épica: {epic_k} — {epic_s}")
    if par_k:
        meta_lines.append(f"Issue padre: {par_k} — {par_s}")

    meta_section = ("\n\nMetadatos del issue:\n" + "\n".join(meta_lines)) if meta_lines else ""

    comments_section = ""
    if comments:
        lines = [f"  [{c['author']}]: {c['body'][:400]}" for c in comments[:5]]
        comments_section = "\n\nComentarios recientes (contexto del equipo):\n" + "\n".join(lines)

    return (
        f"[JIRA: {issue['key']}]\n"
        f"Título: {issue['summary']}\n"
        f"Tipo en Jira: {issue['issue_type']} (genera: {issue['pipeline_type']})\n"
        f"Proyecto: {issue['project_key']}\n"
        f"{meta_section}\n\n"
        f"Descripción del issue:\n{issue['description'] or '(Sin descripción)'}"
        f"{comments_section}"
    )


async def run_pipeline_from_jira(
    issue_ref: str,
    review_callback: Callable[..., str | None] | None,
    event_callback: Callable[[dict[str, Any]], None] | None,
    options: dict[str, Any] | None = None,
):
    """
    Reads Jira issue, runs pipeline, and optionally posts output back to Jira.
    """
    opts = options or {}
    publish_to_jira = bool(opts.get("publish_to_jira", True))
    user_tags = list(opts.get("tags", []) or [])
    include_jira_labels = bool(opts.get("include_jira_labels", True))

    if not (JIRA_BASE_URL and JIRA_EMAIL and JIRA_API_TOKEN):
        raise JiraFlowError("Jira no está configurado (faltan JIRA_BASE_URL/JIRA_EMAIL/JIRA_API_TOKEN)")

    try:
        issue_key = _normalize_key(issue_ref)
    except ValueError as e:
        raise JiraFlowError(str(e)) from e

    jira = JiraClient(JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN)

    try:
        issue = jira.get_issue(issue_key)
    except (JiraAPIError, RuntimeError) as e:
        raise JiraFlowError(f"Error leyendo Jira {issue_key}: {e}") from e

    if event_callback:
        event_callback({
            "type": "jira_issue_loaded",
            "issue_key": issue_key,
            "summary": issue.get("summary", ""),
            "project": issue.get("project_key", ""),
        })

    po_input = build_po_input_from_issue(issue)
    jira_tags = [f"jira-label:{str(lb).strip().lower()}" for lb in issue.get("labels", []) if str(lb).strip()]
    ticket_tags = user_tags + (jira_tags if include_jira_labels else [])

    run = await run_pipeline(
        po_input,
        jira_issue_key=issue_key,
        human_review_callback=review_callback,
        event_callback=event_callback,
        ticket_tags=ticket_tags,
    )

    if publish_to_jira and getattr(run, "ticket_content", ""):
        try:
            jira.update_description(issue_key, run.ticket_content)
            comment_body = (
                f"h3. Openspired — Ticket estructurado\n\n"
                f"*Pipeline ejecutado:* {run.ticket_id}\n"
                f"*Archivo local:* +{run.file_path}+\n\n"
                f"La descripción de este issue fue enriquecida automáticamente por Openspired."
            )
            comment_id = jira.add_comment(issue_key, comment_body)
            if event_callback:
                event_callback({
                    "type": "jira_published",
                    "issue_key": issue_key,
                    "comment_id": comment_id,
                })
        except JiraAPIError as e:
            if event_callback:
                event_callback({
                    "type": "jira_publish_failed",
                    "issue_key": issue_key,
                    "error": str(e),
                })

    return run
