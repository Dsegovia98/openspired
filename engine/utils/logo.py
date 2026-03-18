"""
utils/logo.py — Openspired terminal logo.

Renders a styled ASCII logo using Rich only (no extra dependencies).
Adapts to English or Spanish based on user preference.
"""
from __future__ import annotations

_RICH = False
try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.align import Align
    from rich.columns import Columns
    _RICH = True
except ImportError:
    pass

# ─── ASCII art (hand-crafted, pure box-drawing) ────────────────────────────────
_LOGO_ART = """\
 ██████╗ ██████╗ ███████╗███╗  ██╗███████╗██████╗ ██╗██████╗ ███████╗██████╗
██╔═══██╗██╔══██╗██╔════╝████╗ ██║██╔════╝██╔══██╗██║██╔══██╗██╔════╝██╔══██╗
██║   ██║██████╔╝█████╗  ██╔██╗██║███████╗██████╔╝██║██████╔╝█████╗  ██║  ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚████║╚════██║██╔═══╝ ██║██╔══██╗██╔══╝  ██║  ██║
╚██████╔╝██║     ███████╗██║ ╚███║███████║██║     ██║██║  ██║███████╗██████╔╝
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚══╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝ """

_TAGLINES = {
    "en": "AI-powered ticket generation · From idea to Jira in seconds",
    "es": "Generación de tickets con IA · De idea a Jira en segundos",
}

_SUBTITLES = {
    "en": "open source · product · agents",
    "es": "open source · producto · agentes",
}


def print_logo(lang: str = "en", version: str = "0.1.0") -> None:
    """Print the Openspired terminal logo."""
    tagline  = _TAGLINES.get(lang, _TAGLINES["en"])
    subtitle = _SUBTITLES.get(lang, _SUBTITLES["en"])

    if not _RICH:
        print("\n  OPENSPIRED")
        print(f"  {tagline}\n")
        return

    console = Console()

    logo_text = Text()
    # Gradient: cyan → bright_cyan → white toward the right
    lines = _LOGO_ART.split("\n")
    for line in lines:
        thirds = len(line) // 3
        logo_text.append(line[:thirds],         style="cyan")
        logo_text.append(line[thirds:thirds*2], style="bright_cyan")
        logo_text.append(line[thirds*2:],       style="bold white")
        logo_text.append("\n")

    tagline_text = Text(f"\n  {tagline}", style="dim white")
    tagline_text.append(f"\n  {subtitle}  ·  v{version}", style="dim")

    full = Text()
    full.append_text(logo_text)
    full.append_text(tagline_text)

    console.print()
    console.print(Align.center(full))
    console.print()
