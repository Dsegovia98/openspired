from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import config
from utils.artifacts_index import load_artifacts_index


def _parse_registry_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    content = path.read_text(encoding="utf-8")
    for line in content.splitlines():
        if not re.match(r"^\|\s*(US|DT)-", line.strip()):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8:
            continue
        rows.append(
            {
                "ticket_id": cells[0],
                "ticket_type": cells[1],
                "domain": cells[2],
                "module": cells[3],
                "title": cells[4],
                "date": cells[6],
                "file_path": cells[7].strip("`").strip(),
            }
        )
    return rows


def _normalize_tags(tags_raw: str | list[str] | None) -> list[str]:
    if tags_raw is None:
        return []
    if isinstance(tags_raw, str):
        parts = [p.strip() for p in tags_raw.split(",")]
    else:
        parts = [str(p).strip() for p in tags_raw]

    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tag = re.sub(r"[^a-z0-9:_\-./]+", "-", part.lower()).strip("-")
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def _resolve_ticket_path(file_path: str) -> Path | None:
    if not file_path:
        return None
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    resolved = (config.RUNTIME_PROJECT_ROOT / candidate).resolve()
    if resolved.exists():
        return resolved
    return None


def _read_ticket_meta(file_path: str) -> dict[str, Any]:
    """
    Lee metadata embebida en el ticket final:
      <!-- OPENSPIRED_META ... -->
    """
    path = _resolve_ticket_path(file_path)
    if not path:
        return {}
    try:
        head = path.read_text(encoding="utf-8")[:4000]
    except Exception:
        return {}

    block = re.search(r"<!--\s*OPENSPIRED_META\s*(.*?)-->", head, re.DOTALL)
    if not block:
        return {}

    meta: dict[str, Any] = {}
    for raw_line in block.group(1).splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip().lower()] = val.strip()
    if "tags" in meta:
        meta["tags"] = _normalize_tags(meta.get("tags", ""))
    return meta


def _enrich_with_index(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = load_artifacts_index()
    out: list[dict[str, Any]] = []
    for row in rows:
        ticket_id = row.get("ticket_id", "")
        meta = index.get(ticket_id, {}) if isinstance(index.get(ticket_id, {}), dict) else {}

        file_meta = _read_ticket_meta(str(row.get("file_path", "") or ""))
        tags = _normalize_tags(meta.get("tags", [])) or _normalize_tags(file_meta.get("tags", []))
        enriched = dict(row)
        enriched.update(
            {
                "tags": tags,
                "revisions": int(meta.get("revisions", 0) or 0),
                "input_tokens": int(meta.get("input_tokens", 0) or 0),
                "output_tokens": int(meta.get("output_tokens", 0) or 0),
                "total_tokens": int(meta.get("total_tokens", 0) or 0),
                "cost_usd": float(meta.get("cost_usd", 0.0) or 0.0),
                "run_id": str(meta.get("run_id", "") or ""),
                "po_feedback": str(meta.get("po_feedback", "") or ""),
            }
        )
        out.append(enriched)
    return out


def _trace_logs() -> list[str]:
    trace_logs: list[str] = []
    for p in (config.WORKSPACE_DIR / "logs").glob("*_Trace_Log.md"):
        try:
            trace_logs.append(str(p.relative_to(config.RUNTIME_PROJECT_ROOT)))
        except ValueError:
            trace_logs.append(str(p))
    trace_logs.sort(reverse=True)
    return trace_logs


def _tags_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        for tag in _normalize_tags(item.get("tags", [])):
            summary[tag] = summary.get(tag, 0) + 1
    return dict(sorted(summary.items(), key=lambda kv: (-kv[1], kv[0])))


def _group_by_tags(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        tags = _normalize_tags(item.get("tags", []))
        if not tags:
            grouped.setdefault("untagged", []).append(item)
            continue
        for tag in tags:
            grouped.setdefault(tag, []).append(item)
    return grouped


def list_artifacts(
    ticket_type: str = "",
    module: str = "",
    tags: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 200,
    group_by: str = "",
) -> dict[str, Any]:
    """Returns registry items + trace logs + metadata (tokens/cost/tags)."""
    registro_path = config.WORKSPACE_DIR / "logs" / "_Registro.md"
    rows = _parse_registry_rows(registro_path)
    rows = _enrich_with_index(rows)

    if ticket_type:
        rows = [r for r in rows if r["ticket_type"].lower() == ticket_type.lower()]
    if module:
        rows = [r for r in rows if module.lower() in r["module"].lower()]

    filter_tags = _normalize_tags(tags)
    if filter_tags:
        rows = [
            r for r in rows
            if set(filter_tags).issubset(set(_normalize_tags(r.get("tags", []))))
        ]

    if date_from:
        rows = [r for r in rows if r["date"] >= date_from]
    if date_to:
        rows = [r for r in rows if r["date"] <= date_to]

    rows = rows[: max(1, min(limit, 1000))]
    tags_summary = _tags_summary(rows)

    payload: dict[str, Any] = {
        "registry_path": str(registro_path),
        "items": rows,
        "trace_logs": _trace_logs(),
        "tags_summary": tags_summary,
        "count": len(rows),
    }

    if group_by.lower() in {"tag", "tags"}:
        payload["grouped_by_tags"] = _group_by_tags(rows)

    return payload


def _version_sort_key(path: Path) -> tuple[int, int]:
    name = path.name
    if "human_v" in name:
        m = re.search(r"human_v(\d+)", name)
        return (2, int(m.group(1)) if m else 9999)
    m = re.search(r"_v(\d+)", name)
    return (1, int(m.group(1)) if m else 0)


def _diff_stats(prev_text: str, curr_text: str) -> dict[str, int]:
    prev_lines = prev_text.splitlines()
    curr_lines = curr_text.splitlines()
    matcher = difflib.SequenceMatcher(a=prev_lines, b=curr_lines)

    added = 0
    removed = 0
    unchanged = 0
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "insert":
            added += (j2 - j1)
        elif op == "delete":
            removed += (i2 - i1)
        elif op == "replace":
            removed += (i2 - i1)
            added += (j2 - j1)
        elif op == "equal":
            unchanged += (i2 - i1)

    return {"added": added, "removed": removed, "unchanged": unchanged}


def get_ticket_history(ticket_id: str, include_content: bool = False) -> dict[str, Any]:
    index = load_artifacts_index()
    meta = index.get(ticket_id, {}) if isinstance(index.get(ticket_id, {}), dict) else {}
    row = next((r for r in _parse_registry_rows(config.WORKSPACE_DIR / "logs" / "_Registro.md") if r.get("ticket_id") == ticket_id), {})
    file_meta = _read_ticket_meta(str(row.get("file_path", "") or ""))

    run_id = str(meta.get("run_id", "") or file_meta.get("run_id", "") or "")
    tags = _normalize_tags(meta.get("tags", [])) or _normalize_tags(file_meta.get("tags", []))

    versions: list[dict[str, Any]] = []
    if run_id:
        run_dir = config.LOGS_DIR / "pipeline_runs" / run_id
        if run_dir.exists():
            files = sorted(run_dir.glob("05_ticket*.md"), key=_version_sort_key)
            prev_text = ""
            for fp in files:
                content = fp.read_text(encoding="utf-8")
                stats = _diff_stats(prev_text, content) if prev_text else {"added": len(content.splitlines()), "removed": 0, "unchanged": 0}
                entry = {
                    "name": fp.name,
                    "path": str(fp),
                    "diff": stats,
                }
                if include_content:
                    entry["content"] = content
                versions.append(entry)
                prev_text = content

    return {
        "ticket_id": ticket_id,
        "run_id": run_id,
        "tags": tags,
        "revisions": int(meta.get("revisions", 0) or 0),
        "input_tokens": int(meta.get("input_tokens", 0) or 0),
        "output_tokens": int(meta.get("output_tokens", 0) or 0),
        "total_tokens": int(meta.get("total_tokens", 0) or 0),
        "cost_usd": float(meta.get("cost_usd", 0.0) or 0.0),
        "versions": versions,
        "count": len(versions),
    }
