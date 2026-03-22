"""
map_interface.py — Runner del Agente Mapeador de Interfaz.

Modo de operación:
  1. Playwright navega el producto (si está instalado).
  2. Por cada pantalla: toma screenshot → llama al LLM con visión → extrae estructura.
  3. Acumula el mapa y escribe/actualiza workspace/context/interface_map.md.

Uso:
  python map_interface.py --url https://tu-app.com/dashboard
  python map_interface.py --url https://tu-app.com/dashboard --nav path/to/plantilla.md
  python map_interface.py --screenshots-dir ./capturas/  # solo analiza screenshots existentes

Requiere: pip install playwright && playwright install chromium
Si Playwright no está disponible, usa el modo --screenshots-dir con capturas manuales.
"""
from __future__ import annotations
import argparse
import base64
import json
import sys
import time
import re
from pathlib import Path
from datetime import datetime

# ─── Asegurar que el engine esté en el path ───────────────────────────────────
_ENGINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_ENGINE_DIR))

from config import WORKSPACE_DIR, RUNTIME_PROJECT_ROOT, resolve_agent_path
from agents.base import run_agent
from context.builder import _read, _section


# ─── Prompt del Mapeador ──────────────────────────────────────────────────────

def _mapeador_system_prompt() -> str:
    """Construye el system prompt del Mapeador con su definición y skill."""
    agent_def   = _read(resolve_agent_path("09_Mapeador_Interfaz/09_Mapeador_Interfaz.md")) or ""
    skill_nav   = _read(resolve_agent_path("09_Mapeador_Interfaz/Skills/01_Skill_Navegacion_Fractal_Mapa.md")) or ""
    global_rules = _read(WORKSPACE_DIR / "context" / "global.md") or ""
    current_map  = _read(WORKSPACE_DIR / "context" / "interface_map.md") or ""

    parts = ["# AGENT CONTEXT: MAPEADOR DE INTERFAZ\n"]
    if global_rules:
        parts.append(_section("UNIVERSAL RULES", global_rules))
    if current_map:
        parts.append(_section("INTERFACE MAP ACTUAL (no borrar — solo agregar/completar)", current_map))
    if agent_def:
        parts.append(_section("AGENT DEFINITION", agent_def))
    if skill_nav:
        parts.append(_section("SKILL: NAVEGACIÓN FRACTAL", skill_nav))
    return "".join(parts)


def _screenshot_analysis_prompt(screenshot_b64: str, url: str, nav_context: str = "") -> str:
    """Prompt para analizar un screenshot y extraer estructura de interfaz."""
    nav_section = f"\nCONTEXTO DE NAVEGACIÓN (qué áreas/módulos priorizar):\n{nav_context}\n" if nav_context else ""
    return f"""Eres el Mapeador de Interfaz. Estás analizando un screenshot de la aplicación.

URL actual: {url}
{nav_section}
Tu tarea con este screenshot:
1. Identifica el Área y Módulo donde estás (usa el breadcrumb, título o menú lateral).
2. Identifica el nombre de la pantalla actual.
3. Documenta:
   - Estados visibles (normal, vacío, error, cargando — solo los que VES en la imagen)
   - Acciones disponibles (botones, íconos de acción — lista exactamente los textos que aparecen)
   - Columnas de tabla si hay una tabla
   - Cualquier modal o panel de detalle visible

Produce tu análisis en el formato estándar del interface_map.md:

```
### [Módulo identificado]
- **[Nombre de Pantalla]**
  - Estados: [lo que ves]
  - Acceso: FULL ([acciones visibles]) | BASIC (verificar restricciones)
  - Descripción: [qué hace esta pantalla, qué información muestra]
```

Si no puedes identificar claramente el módulo o la pantalla, escribe lo que sí puedes ver y agrega "(verificar)" al final."""


def _build_final_map_prompt(sections: list[str], nav_context: str = "") -> str:
    """Prompt para que el Mapeador consolide todos los análisis en un interface_map.md final."""
    current_map = _read(WORKSPACE_DIR / "context" / "interface_map.md") or ""
    nav_section = f"\nPLANTILLA DE NAVEGACIÓN USADA:\n{nav_context}\n" if nav_context else ""

    return f"""Eres el Mapeador de Interfaz. Has analizado {len(sections)} screenshot(s) del producto.
{nav_section}
MAPA EXISTENTE (no borrar — solo agregar o mejorar secciones):
{current_map}

ANÁLISIS DE CADA PANTALLA EXPLORADA:
{"=" * 60}
{chr(10).join(f"--- Pantalla {i+1} ---{chr(10)}{s}" for i, s in enumerate(sections))}
{"=" * 60}

Tu tarea: Produce el `interface_map.md` completo y actualizado.
- Organiza por jerarquía: Área → Módulo → Pantalla
- Integra las pantallas nuevas con las que ya existían en el mapa
- Usa el formato estándar del skill de Navegación Fractal
- No dupliques pantallas — si una ya existía, enriquece su descripción
- Marca como `(pendiente de exploración)` las secciones que se saben que existen pero no se exploraron

Produce ÚNICAMENTE el contenido del interface_map.md (empezando con el header del archivo).
No agregues explicaciones fuera del formato del mapa."""


# ─── Playwright: navegación automática ───────────────────────────────────────

def _run_with_playwright(url: str, nav_context: str) -> list[tuple[str, str]]:
    """
    Navega la URL con Playwright, toma screenshots por sección y retorna
    lista de (url, screenshot_base64).

    Si Playwright no está instalado, lanza ImportError (el caller lo maneja).
    """
    from playwright.sync_api import sync_playwright  # type: ignore

    screenshots: list[tuple[str, str]] = []

    with sync_playwright() as p:
        print("  Abriendo navegador (Chromium)...")
        browser = p.chromium.launch(headless=False)  # headless=False: el PO puede ver lo que pasa
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        print(f"  Navegando a: {url}")
        page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(2)  # esperar render inicial

        # Screenshot de la pantalla inicial
        shot = page.screenshot(full_page=False)
        screenshots.append((page.url, base64.b64encode(shot).decode()))
        print(f"  ✓ Screenshot 1: {page.url}")

        # Intentar navegar por los ítems del menú principal
        # Buscar links de navegación (sidebar, navbar)
        nav_selectors = [
            "nav a",
            "[role='navigation'] a",
            ".sidebar a",
            ".nav-menu a",
            ".menu-item a",
            "[data-testid*='nav'] a",
            "[class*='sidebar'] a",
            "[class*='menu'] a",
        ]

        nav_links: list[dict] = []
        for selector in nav_selectors:
            try:
                links = page.query_selector_all(selector)
                if links:
                    for link in links[:15]:  # máx 15 links de nav
                        href = link.get_attribute("href") or ""
                        text = link.inner_text().strip()
                        if text and href and not href.startswith("#") and len(text) > 1:
                            nav_links.append({"text": text, "href": href})
                    if nav_links:
                        break
            except Exception:
                continue

        if nav_links:
            print(f"  Encontrados {len(nav_links)} links de navegación")
            base_url = "/".join(url.split("/")[:3])
            visited = {page.url}

            for i, link in enumerate(nav_links[:10]):  # máx 10 secciones
                href = link["href"]
                if not href.startswith("http"):
                    href = base_url + href if href.startswith("/") else base_url + "/" + href
                if href in visited:
                    continue

                try:
                    print(f"  Navegando a: {link['text']} ({href})")
                    page.goto(href, wait_until="networkidle", timeout=15000)
                    time.sleep(1.5)
                    visited.add(page.url)

                    shot = page.screenshot(full_page=False)
                    screenshots.append((page.url, base64.b64encode(shot).decode()))
                    print(f"  ✓ Screenshot {len(screenshots)}: {link['text']}")
                except Exception as e:
                    print(f"  ⚠ No se pudo navegar a {link['text']}: {e}")

        browser.close()

    return screenshots


def _load_screenshots_from_dir(directory: str) -> list[tuple[str, str]]:
    """Carga screenshots PNG/JPG de un directorio y los convierte a base64."""
    shots = []
    for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
        for f in sorted(Path(directory).glob(ext)):
            data = f.read_bytes()
            shots.append((f.name, base64.b64encode(data).decode()))
    return shots


# ─── Análisis de screenshots con vision ───────────────────────────────────────

def _analyze_screenshot_with_vision(screenshot_b64: str, url: str, nav_context: str) -> str:
    """
    Llama al LLM con un screenshot para que identifique la estructura de la pantalla.

    Usa la API de visión nativa del proveedor configurado.
    """
    # Intentar con el proveedor configurado
    try:
        from config import (
            PROVIDER, DEFAULT_MODEL,
            ANTHROPIC_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY,
        )
        import urllib.request

        provider = (PROVIDER or "").lower()
        model = DEFAULT_MODEL

        if provider == "anthropic":
            if not ANTHROPIC_API_KEY:
                return "(Error: ANTHROPIC_API_KEY no configurada)"
            payload = {
                "model": model,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": _screenshot_analysis_prompt("", url, nav_context),
                            },
                        ],
                    }
                ],
            }
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=json.dumps(payload).encode(),
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result["content"][0]["text"]

        elif provider == "google":
            if not GOOGLE_API_KEY:
                return "(Error: GOOGLE_API_KEY no configurada)"
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"inline_data": {"mime_type": "image/png", "data": screenshot_b64}},
                            {"text": _screenshot_analysis_prompt("", url, nav_context)},
                        ]
                    }
                ]
            }
            google_model = model or "gemini-2.5-flash-lite"
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{google_model}:generateContent?key={GOOGLE_API_KEY}"
            req = urllib.request.Request(
                api_url,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                return result["candidates"][0]["content"]["parts"][0]["text"]

        elif provider == "openai":
            if not OPENAI_API_KEY:
                return "(Error: OPENAI_API_KEY no configurada)"
            openai_model = model or "gpt-4o-mini"
            payload = {
                "model": openai_model,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _screenshot_analysis_prompt("", url, nav_context)},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}},
                        ],
                    }
                ],
            }
            req = urllib.request.Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read())
                choices = result.get("choices") or []
                if not choices:
                    return f"(Error OpenAI: respuesta sin choices: {result})"
                return choices[0]["message"]["content"]

        else:
            return f"(Proveedor '{provider}' no soporta visión en este script. Agrega soporte o usa --screenshots-dir con análisis manual.)"

    except Exception as e:
        return f"(Error al analizar screenshot con visión: {e})"


# ─── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mapea la interfaz de un producto web y genera interface_map.md"
    )
    parser.add_argument(
        "--url", "-u",
        help="URL de entrada del producto (punto de inicio de la navegación)",
    )
    parser.add_argument(
        "--nav", "-n",
        help="Ruta a la plantilla de navegación (00_Plantilla_Navegacion.md)",
        default=None,
    )
    parser.add_argument(
        "--screenshots-dir", "-s",
        help="Directorio con screenshots existentes (modo sin Playwright)",
        default=None,
    )
    parser.add_argument(
        "--output", "-o",
        help="Ruta del archivo de salida (default: workspace/context/interface_map.md)",
        default=None,
    )
    args = parser.parse_args()

    if not args.url and not args.screenshots_dir:
        parser.error("Se requiere --url o --screenshots-dir")

    if args.output:
        output_path = Path(args.output).expanduser()
        if not output_path.is_absolute():
            output_path = (RUNTIME_PROJECT_ROOT / output_path).resolve()
        else:
            output_path = output_path.resolve()
        try:
            output_path.relative_to(RUNTIME_PROJECT_ROOT.resolve())
        except ValueError:
            parser.error(f"--output debe estar dentro del profile runtime: {RUNTIME_PROJECT_ROOT}")
    else:
        output_path = WORKSPACE_DIR / "context" / "interface_map.md"

    # Leer plantilla de navegación si se proporcionó
    nav_context = ""
    if args.nav:
        nav_path = Path(args.nav)
        if nav_path.exists():
            nav_context = nav_path.read_text(encoding="utf-8")
            print(f"  ✓ Plantilla de navegación: {nav_path}")
        else:
            print(f"  ⚠ Plantilla no encontrada: {nav_path}")

    print("\n" + "=" * 60)
    print("  MAPEADOR DE INTERFAZ — Openspired")
    print("=" * 60)

    # ── Obtener screenshots ────────────────────────────────────────────────────
    screenshots: list[tuple[str, str]] = []

    if args.screenshots_dir:
        print(f"\n  Modo manual: cargando screenshots de {args.screenshots_dir}")
        screenshots = _load_screenshots_from_dir(args.screenshots_dir)
        print(f"  ✓ {len(screenshots)} screenshot(s) cargados")
    else:
        print(f"\n  Intentando navegación automática con Playwright...")
        try:
            screenshots = _run_with_playwright(args.url, nav_context)
        except ImportError:
            print(
                "\n  ⚠ Playwright no está instalado.\n"
                "  Para instalar: pip install playwright && playwright install chromium\n"
                "\n  Alternativa: toma screenshots manualmente y usa:\n"
                f"  python map_interface.py --screenshots-dir ./capturas/\n"
            )
            sys.exit(1)
        except Exception as e:
            print(f"\n  ⛔ Error durante la navegación: {e}")
            sys.exit(1)

    if not screenshots:
        print("\n  ⛔ No se encontraron screenshots para analizar.")
        sys.exit(1)

    # ── Analizar cada screenshot con visión ────────────────────────────────────
    print(f"\n  Analizando {len(screenshots)} pantalla(s) con visión IA...")
    section_analyses: list[str] = []

    for i, (url_or_name, shot_b64) in enumerate(screenshots):
        print(f"  [{i+1}/{len(screenshots)}] {url_or_name}")
        analysis = _analyze_screenshot_with_vision(shot_b64, url_or_name, nav_context)
        section_analyses.append(analysis)
        time.sleep(0.5)  # rate limiting

    # ── Consolidar en interface_map.md final ──────────────────────────────────
    print("\n  Consolidando mapa de interfaz...")
    sys_prompt   = _mapeador_system_prompt()
    final_prompt = _build_final_map_prompt(section_analyses, nav_context)
    final_map    = run_agent("mapeador", sys_prompt, final_prompt)

    # ── Escribir resultado ─────────────────────────────────────────────────────
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Backup del mapa anterior si existe
    if output_path.exists():
        backup_path = output_path.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
        backup_path.write_text(output_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"  ✓ Backup guardado: {backup_path.name}")

    output_path.write_text(final_map, encoding="utf-8")

    print(f"\n  ✅ Interface map actualizado: {output_path}")
    print(f"  Pantallas mapeadas: {len(screenshots)}")
    print("\n  El pipeline de openspired ya puede usar este mapa para:")
    print("  • Identificar la pantalla exacta de cada ticket (campo `screen` en el YAML)")
    print("  • Calibrar el nivel de especificidad de Dev Concepto y Escritor")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
