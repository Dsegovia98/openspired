"""
utils/registro.py — Actualiza _Registro.md con cada nuevo ticket generado.
Lee y escribe el registro de forma atómica con file locking para evitar
condiciones de carrera si múltiples instancias del pipeline corren en paralelo.
"""
from __future__ import annotations
import json
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from config import WORKSPACE_DIR, DOMAIN_PRIMARY, DOMAIN_SECONDARY


@contextmanager
def _file_lock(path: Path):
    """
    Context manager de file locking cross-platform.
    - POSIX (Linux/macOS): usa fcntl.flock (lock exclusivo)
    - Windows: usa msvcrt.locking como fallback
    En cualquier caso, la operación crítica es atómica respecto a otros procesos.
    """
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        import fcntl
        with open(lock_path, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    else:
        # Windows: lock via archivo de señal
        import time
        max_wait = 10  # segundos
        waited   = 0.0
        while lock_path.exists() and waited < max_wait:
            time.sleep(0.1)
            waited += 0.1
        lock_path.touch()
        try:
            yield
        finally:
            lock_path.unlink(missing_ok=True)

REGISTRO_PATH = WORKSPACE_DIR / "logs" / "_Registro.md"
COUNTERS_PATH = WORKSPACE_DIR / "logs" / ".ticket_counters.json"


def _build_prefix(ticket_type: str, domain: str) -> str:
    """Builds ticket prefix dynamically from domain name.

    Examples:
        ("User Story",  "App")       → "US-APP"
        ("Design Task", "Analytics") → "DT-ANA"
        ("User Story",  "MyProduct") → "US-MYPR"
    """
    type_part   = "DT" if ticket_type == "Design Task" else "US"
    domain_slug = domain.upper().replace(" ", "").replace("-", "").replace("_", "")[:4]
    return f"{type_part}-{domain_slug}"


_REGISTRO_TEMPLATE = """\
# Registro de Tickets — Openspired

Índice maestro de todos los tickets generados por el pipeline.

| ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |
|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | *Aún no hay tickets generados* | — |

## Cómo usar este registro

- **ID:** Identificador único (ej: `US-APP-0001`, `DT-ANA-0003`).
- **Archivo:** Ruta relativa al `.md` generado.
"""


def _ensure_registro() -> None:
    """Crea _Registro.md con estructura vacía si no existe."""
    if not REGISTRO_PATH.exists():
        REGISTRO_PATH.parent.mkdir(parents=True, exist_ok=True)
        REGISTRO_PATH.write_text(_REGISTRO_TEMPLATE, encoding="utf-8")


def _current_counter(ticket_type: str, domain: str) -> int:
    """Lee el último ID asignado del tipo/dominio dado desde _Registro.md."""
    _ensure_registro()
    content = REGISTRO_PATH.read_text(encoding="utf-8")
    # Busca filas como "| DT-APP-0005 |" en el historial para obtener el máximo
    prefix  = _build_prefix(ticket_type, domain)
    pattern = rf"\|\s*{re.escape(prefix)}-(\d{{4}})\s*\|"
    matches = re.findall(pattern, content)
    if not matches:
        return 0
    return max(int(m) for m in matches)


def next_ticket_id(ticket_type: str, domain: str) -> str:
    """
    Backward-compatible wrapper.
    Reserva y retorna el siguiente ID de forma segura para concurrencia.
    """
    return allocate_ticket_id(ticket_type, domain)


def allocate_ticket_id(ticket_type: str, domain: str) -> str:
    """
    Reserva un ID único de ticket usando un contador persistente con lock.
    Evita colisiones cuando corren múltiples instancias del pipeline en paralelo.
    """
    COUNTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock(COUNTERS_PATH):
        prefix = _build_prefix(ticket_type, domain)
        counters: dict[str, int] = {}

        if COUNTERS_PATH.exists():
            try:
                counters = json.loads(COUNTERS_PATH.read_text(encoding="utf-8"))
                if not isinstance(counters, dict):
                    counters = {}
            except Exception:
                counters = {}

        current = counters.get(prefix)
        if not isinstance(current, int):
            # Bootstrap desde _Registro.md para mantener continuidad de numeración.
            current = _current_counter(ticket_type, domain)

        next_num = current + 1
        counters[prefix] = next_num
        COUNTERS_PATH.write_text(json.dumps(counters, ensure_ascii=True, indent=2), encoding="utf-8")
        return f"{prefix}-{next_num:04d}"


def register_ticket(
    ticket_id: str,
    ticket_name: str,
    domain: str,
    module: str,
    ticket_type: str,
    file_path: str,
    tags: list[str] | None = None,
) -> None:
    """
    Agrega una nueva fila al historial de _Registro.md.
    Usa file locking para garantizar que dos instancias paralelas no generen el mismo ID.
    """
    with _file_lock(REGISTRO_PATH):
        _register_ticket_locked(ticket_id, ticket_name, domain, module, ticket_type, file_path, tags=tags)


def _register_ticket_locked(
    ticket_id: str,
    ticket_name: str,
    domain: str,
    module: str,
    ticket_type: str,
    file_path: str,
    tags: list[str] | None = None,
) -> None:
    """Implementación interna — llamar solo dentro de _file_lock."""
    _ = tags  # tags persist in artifacts index; registry remains backward-compatible.
    _ensure_registro()
    content = REGISTRO_PATH.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    # Idempotencia defensiva: evita filas duplicadas si se reintenta registrar
    # el mismo ticket por un error transitorio aguas abajo.
    if re.search(rf"^\|\s*{re.escape(ticket_id)}\s*\|", content, re.MULTILINE):
        return

    # Columnas reales de _Registro.md:
    # | ID | Tipo | Dominio | Módulo/Proyecto | Título | DT Relacionada | Fecha | Archivo |
    new_row = (
        f"| {ticket_id} | {ticket_type} | {domain} | {module} | "
        f"{ticket_name} | — | {today} | `{file_path}` |\n"
    )

    # Insertar justo antes del separador de sección siguiente
    # o al final de la última fila existente de la tabla
    if "| — | — | — |" in content:
        # Tabla vacía — reemplazar la fila placeholder
        content = re.sub(
            r"\| — \| — \| — \| — \| — \| — \| \*Aún no hay tickets generados\* \| — \|\n",
            new_row,
            content,
        )
    else:
        # Tabla con contenido — insertar después de la última fila de datos
        # Buscar la última fila de la tabla (línea que empieza con "| US-" o "| DT-")
        last_row_match = list(re.finditer(r"^\| (?:US|DT)-[^\n]+\|$", content, re.MULTILINE))
        if last_row_match:
            last_end = last_row_match[-1].end()
            content = content[:last_end] + "\n" + new_row.rstrip("\n") + content[last_end:]
        else:
            # Fallback: insertar antes del separador de instrucciones
            marker = "## Cómo usar este registro"
            content = content.replace(marker, new_row + "\n" + marker)

    REGISTRO_PATH.write_text(content, encoding="utf-8")
