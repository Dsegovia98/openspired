# Openspired — Pipeline Multi-Agente

Sistema de agentes con contextos completamente aislados.
Cada agente = una llamada API independiente. Sin contaminación de contexto.

---

## Instalación (una sola vez)

```bash
# 1. Ir al directorio del pipeline
cd engine

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar API key
cp .env.example .env
# Abre .env y agrega tu ANTHROPIC_API_KEY

# 4. Verificar que todo está OK
python run.py --check
```

---

## Uso

```bash
# Modo interactivo (te pide el requerimiento)
python run.py

# Input directo
python run.py "Agregar sección de logs al módulo de Support para registrar cambios en service cards"

# Verificar configuración
python run.py --check
```

---

## Qué hace el pipeline

```
[Tu requerimiento]
       │
       ▼
① Orquestador     → Clasifica y genera el Manifiesto YAML
       │
  ┌────┴────┐
  ▼         ▼
② Ideador  Researcher   ← PARALELO (2x más rápido)
  └────┬────┘
       ▼
③ Desarrollador de Concepto  → Arquitectura, edge cases, roles
       │
       ▼
④ Escritor de USs  → Ticket bilingüe en texto plano
       │
  ┌────┴────┐
  ▼         ▼
⑤ QA      Feedback  ← PARALELO + Anti-loop (máx 2 revisiones)
  └────┬────┘
       │ (si hay issues → vuelve a ④, máx 2 veces)
       ▼
⑥ Documentador  → Guarda ticket + actualiza _Registro.md
       │
       ▼
⑦ Meta-Observador  → Aprende + actualiza ReasoningBank + Memory
```

---

## Outputs generados

| Archivo | Descripción |
|---------|-------------|
| `Cake/Tickets/.../ID_Nombre.md` | Ticket final listo para Jira |
| `_Registro.md` | Registro actualizado con el nuevo ticket |
| `.logs/ID_Trace_Log.md` | Trazabilidad completa de la ejecución |
| `.logs/pipeline_runs/[run_id]/` | Documentos de handoff intermedios |
| `Sistema/.meta_insights/audit_log_ID.md` | Auditoría del Meta-Observador |
| `Sistema/.reasoning_bank/patrones_exitosos.md` | Patrones aprendidos (auto-actualizado) |

---

## Estructura del código

```
pipeline/
├── run.py              ← Entry point (aquí ejecutas)
├── pipeline.py         ← Orquestador del pipeline completo
├── config.py           ← Configuración y auto-detección de rutas
├── requirements.txt
├── .env.example
├── agents/
│   └── base.py         ← Runner aislado de agente (1 agente = 1 llamada API)
├── context/
│   └── builder.py      ← Ensambla el contexto mínimo por agente
└── utils/
    ├── display.py      ← UI de terminal con rich
    ├── trace_log.py    ← Generación de Trace Logs
    ├── registro.py     ← Actualización de _Registro.md
    └── file_io.py      ← Operaciones de archivos
```
