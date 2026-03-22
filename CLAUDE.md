# Openspired — Contexto para Claude

## Qué es este proyecto

Pipeline multi-agente que convierte requisitos de producto en tickets estructurados de Jira. 9 agentes especializados en secuencia: Orquestador → Researcher → Desarrollador de Concepto → Escritor → QA → Revisión Humana → Documentador → Meta-Observer.

El usuario describe un requisito en lenguaje natural (o pega una URL de Jira), el pipeline lo procesa, genera un ticket bilingüe (ES/EN), espera aprobación humana y lo publica en Jira.

---

## Stack

```
openspired/
├── engine/          Python 3.10+ — pipeline core, FastAPI, agentes
├── agents/          Definiciones de agentes en Markdown
├── desktop/         Tauri v2 + React/TypeScript — app de escritorio macOS
├── workspace/       Datos del usuario — GITIGNORED
└── templates/       Templates de onboarding
```

### Backend (engine/)
- **FastAPI** en `engine/api_server.py` — puerto 8765, solo localhost
- **Pipeline** en `engine/pipeline.py` — lógica principal de los 9 agentes
- **RunManager** en `engine/application/run_manager.py` — cola de runs, SSE events, human review gate
- **Profile system** en `engine/profile_loader.py` — aislamiento de datos por perfil
- **Providers** en `engine/providers/` — Google (Gemini), Anthropic (Claude), OpenAI

### Frontend (desktop/)
- **App.tsx** — componente raíz, todas las vistas definidas como funciones internas
- **styles.css** — design tokens OKLCH, sistema completo de componentes
- **api/client.ts** — fetch wrapper, SSE streaming via ReadableStream (NO EventSource)
- **desktop/bootstrap.ts** — arranque del backend Tauri via invoke()

---

## Sistema de perfiles — CRÍTICO

Tauri setea `OPENSPIRED_PROFILE_PATH` al arrancar apuntando a:
```
~/Library/Application Support/com.openspired.desktop/runtime/
```

Ahí viven:
- `.env` — API keys del usuario
- `workspace/` — tickets generados, ideas, historial, módulos
- `logs/` — runs y el `.api_token` de sesión

**El código del repo NUNCA toca ese directorio.** Todo acceso a `.env` pasa por `config.ENV_FILE` que resuelve via `profile_loader.py`. Reinstalar el `.dmg` no borra estos datos.

---

## API — Endpoints principales

Base URL: `http://127.0.0.1:8765`
Auth: `Authorization: Bearer {token}` (token en `workspace/logs/.api_token`)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/health` | Sin auth — status del backend |
| GET/POST | `/setup` | Sin auth — leer/escribir configuración |
| POST | `/runs` | Crear run (mode: manual \| jira) |
| GET | `/runs/{id}` | Estado de un run |
| GET | `/runs/{id}/events` | SSE stream de eventos |
| POST | `/runs/{id}/review` | Acción humana (approve/feedback/discard) |
| GET | `/artifacts` | Historial de tickets generados |
| GET | `/ideas` | Listar ideas pre-backlog |
| POST | `/ideas` | Capturar idea (sin AI) |
| GET | `/jira/test` | Diagnóstico de conectividad Jira |

### Estructura de eventos SSE

```json
{
  "id": 1,
  "run_id": "run_abc123",
  "type": "review_required",
  "timestamp": "2026-03-22T...",
  "payload": {
    "ticket_text": "...",
    "ticket_type": "User Story",
    "module": "analytics",
    "revision": 0
  }
}
```

**IMPORTANTE:** Los datos del evento están en `event.payload`, no en la raíz del objeto. El frontend lee `e.payload` para review_required.

---

## Frontend — Patrones y reglas

### Bug crítico resuelto — no volver a introducir

Las vistas (`CreateView`, `PipelineView`, `SettingsView`, etc.) están definidas como funciones **dentro** de `App()`. Si se usan como `<PipelineView />` (componentes), React las desmonta y remonta en cada render del padre porque la referencia cambia — esto hace que los inputs pierdan el foco con cada tecla.

**Solución correcta:** llamarlas como funciones `{PipelineView()}` en el render. Así React las trata como JSX inline y no crea un boundary de componente.

### SSE — usar fetch, NO EventSource

`EventSource` no soporta headers de Authorization. El streaming se hace con `fetch` + `ReadableStream` en `api/client.ts → streamRunEvents()`.

### CORS — OPTIONS debe pasar antes del auth check

En `api_server.py`, el middleware de auth debe dejar pasar las requests `OPTIONS` antes de verificar el token, si no el preflight de CORS falla con 401.

### Settings — keys ya guardadas

El `GET /setup` devuelve `"***set***"` para los campos secretos. El frontend muestra "✓ Configurada" + botón "Cambiar" en lugar de un input vacío. No mostrar nunca un campo de API key vacío cuando ya hay una configurada.

### Esperar backend tras restart

Después de `restartDesktopBackend()`, el backend tarda unos segundos. Hay un loop de retry contra `/health` con hasta 10 segundos de espera antes de hacer cualquier llamada autenticada.

---

## Tipos de ticket

Solo existen dos tipos en el pipeline:
- **User Story** — funcionalidad de producto
- **Design Task** — trabajo de diseño

El Orquestador clasifica automáticamente. El usuario puede dar una pista explícita con `ticketTypeHint` que se prepende al input como `"TIPO SOLICITADO: Design Task\n\n{input}"`.

PRD e Investigación NO son modos separados del pipeline — son partes internas del pipeline estándar.

---

## Jira

- `engine/utils/jira_client.py` — wrapper sobre Jira REST API (urllib puro, sin deps)
- Lee v3 (ADF) para contenido, escribe en v2 (wiki markup)
- `_normalize_key()` acepta URL completa (`https://.../browse/CAKE-6539`) o solo la key
- Error 401 = token inválido o expirado (los tokens de Atlassian expiran)
- Error 404 = issue no existe en ese workspace o el token no tiene permiso

---

## Comandos de build

```bash
# Arrancar en modo desarrollo
cd desktop && npm run tauri dev

# Build de producción (universal macOS — Apple Silicon + Intel)
export PATH="$HOME/.cargo/bin:$PATH"
npm run tauri build -- --target universal-apple-darwin

# Crear .dmg
hdiutil create -volname "Openspired" \
  -srcfolder "src-tauri/target/universal-apple-darwin/release/bundle/macos/Openspired Desktop.app" \
  -ov -format UDZO Openspired.dmg

# GitHub release
/opt/homebrew/bin/gh release create vX.Y.Z Openspired.dmg \
  --title "Openspired vX.Y.Z" --notes "..."
```

El `.dmg` está en `.gitignore` — nunca commitearlo. Siempre subir como asset de GitHub Release.

---

## Bugs ya resueltos — no reintroducir

| Bug | Causa | Fix |
|-----|-------|-----|
| Focus loss en textarea | Vistas como `<Component />` dentro de App | Llamarlas como `{Component()}` |
| CORS 401 en preflight | Middleware auth bloqueaba OPTIONS | Bypass OPTIONS antes del check |
| `bad character range \\-.` | `[^a-z0-9:_\\-./]` en regex | Mover guión al final: `[^a-z0-9:_./-]` |
| Review card vacío | `e.ticket_text` undefined | Leer `e.payload.ticket_text` |
| Error al guardar settings | `apiGet` inmediato tras restart | Loop retry contra `/health` hasta 10s |
| SSE 401 | EventSource sin auth header | Usar fetch + ReadableStream |

---

## Datos del usuario — aislamiento

```
~/Library/Application Support/com.openspired.desktop/runtime/
├── .env                          # API keys
└── workspace/
    ├── tickets/                  # Tickets generados
    ├── ideas/                    # Ideas pre-backlog
    ├── artifacts/                # USs, DTs aprobadas
    ├── context/                  # Contexto de producto, sprint, módulos
    └── logs/
        ├── .api_token            # Token de sesión (regenerado en cada arranque)
        └── pipeline_runs/        # Historial de runs
```

Reinstalar la app no borra estos datos. Solo se borran manualmente o con un "reset" desde la app (que no existe aún).

---

## GitHub

- Repo: `https://github.com/Dsegovia98/openspired`
- Remote: `origin`
- Branch principal: `master`
- Releases con `.dmg`: `https://github.com/Dsegovia98/openspired/releases`
