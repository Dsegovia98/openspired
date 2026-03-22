"""
ideas_service.py — Pre-backlog idea capture and listing.

Ideas are raw, unprocessed concepts saved to the workspace for later
promotion to the full pipeline. No AI agents are involved.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def _ideas_dir() -> Path:
    d = config.WORKSPACE_DIR / "ideas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _index_path() -> Path:
    return _ideas_dir() / "_Ideas_Pendientes.md"


def _slug(text: str, max_len: int = 40) -> str:
    """Convert text to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:max_len].strip("_")


def _ensure_index() -> None:
    idx = _index_path()
    if not idx.exists():
        idx.write_text(
            "# Ideas Pendientes\n\n"
            "| Fecha | Nombre | Dominio | Origen | Estado |\n"
            "|-------|--------|---------|--------|--------|\n",
            encoding="utf-8",
        )


def capture_idea(
    title: str,
    description: str,
    domain: str = "App",
    origin: str = "Manual",
) -> dict[str, Any]:
    """
    Save a raw idea to the pre-backlog.
    Returns metadata about the saved idea.
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    slug = _slug(title)
    filename = f"{date_str}_{slug}.md"
    idea_path = _ideas_dir() / filename

    content = (
        f"---\n"
        f"Fecha: {date_str}\n"
        f"Dominio: {domain}\n"
        f"Estado: 💡 Cruda\n"
        f"Origen: {origin}\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"## Descripción\n\n"
        f"{description}\n\n"
        f"## Contexto adicional\n\n"
        f"[PENDIENTE]\n\n"
        f"## Próximos pasos\n\n"
        f"- [ ] Madurar la idea\n"
        f"- [ ] Promover al pipeline con `/generar_slice` o `/generar_prd`\n"
    )
    idea_path.write_text(content, encoding="utf-8")

    _ensure_index()
    with open(_index_path(), "a", encoding="utf-8") as f:
        f.write(f"| {date_str} | {title} | {domain} | {origin} | 💡 Cruda |\n")

    return {
        "status": "ok",
        "filename": filename,
        "path": str(idea_path),
        "date": date_str,
        "title": title,
        "domain": domain,
    }


def list_ideas(limit: int = 50) -> list[dict[str, Any]]:
    """List saved ideas from the pre-backlog, newest first."""
    ideas_dir = _ideas_dir()
    files = sorted(
        [f for f in ideas_dir.glob("*.md") if not f.name.startswith("_")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    results = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
            # Parse frontmatter
            meta: dict[str, str] = {}
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    for line in parts[1].splitlines():
                        if ":" in line:
                            k, _, v = line.partition(":")
                            meta[k.strip()] = v.strip()
            results.append({
                "filename": f.name,
                "title": meta.get("Fecha", f.stem),
                "date": meta.get("Fecha", ""),
                "domain": meta.get("Dominio", ""),
                "status": meta.get("Estado", "💡 Cruda"),
                "origin": meta.get("Origen", ""),
            })
        except Exception:
            continue
    return results
