<div align="center">

```
 ██████╗ ██████╗ ███████╗███╗   ██╗███████╗██████╗ ██╗██████╗ ███████╗██████╗
██╔═══██╗██╔══██╗██╔════╝████╗  ██║██╔════╝██╔══██╗██║██╔══██╗██╔════╝██╔══██╗
██║   ██║██████╔╝█████╗  ██╔██╗ ██║███████╗██████╔╝██║██████╔╝█████╗  ██║  ██║
██║   ██║██╔═══╝ ██╔══╝  ██║╚██╗██║╚════██║██╔═══╝ ██║██╔══██╗██╔══╝  ██║  ██║
╚██████╔╝██║     ███████╗██║ ╚████║███████║██║     ██║██║  ██║███████╗██████╔╝
 ╚═════╝ ╚═╝     ╚══════╝╚═╝  ╚═══╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝
```

**Un pipeline multi-agente que convierte requerimientos de producto en tickets de Jira estructurados — desde tu terminal.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Providers](https://img.shields.io/badge/AI-Google%20%7C%20Anthropic%20%7C%20OpenAI-blueviolet)](#proveedores-de-ia)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[English](README.md) · **Español**

</div>

---

## La convicción detrás de este proyecto

Cuando escribir código se vuelve una commodity, el valor del producto se concentra en otro lugar: en **entender el problema a fondo**, en **diseñar la solución correcta**, y en **el juicio humano que decide qué construir y por qué**.

Discovery, definición, validación de hipótesis — estas son las actividades que hacen avanzar los productos y que no se pueden delegar a la automatización. Sin embargo, la mayoría de los equipos de producto pasan una cantidad desproporcionada de tiempo en trabajo operativo: estructurar tickets, traducir requerimientos en criterios de aceptación, documentar lo que ya se decidió en una reunión.

**Openspired libera ese tiempo.**

Describe lo que necesitas en lenguaje natural. Un pipeline de 9 agentes especializados se encarga del resto — orquestación, investigación, desarrollo de concepto, redacción, QA — y entrega un ticket estructurado, bilingüe y listo para publicar. Cada ejecución le enseña al sistema sobre tu producto, por lo que con el tiempo se vuelve más preciso con menos input de tu parte.

El objetivo no es reemplazar el pensamiento de producto. Es hacer espacio para más.

---

## Qué hace

Describes un requerimiento en lenguaje natural (o pegas un link de Jira). Openspired ejecuta 9 agentes especializados en secuencia y produce un ticket completamente estructurado y bilingüe (EN/ES) listo para revisar y publicar.

Antes de escribir nada, los agentes consultan el contexto acumulado de tu producto — historial de módulos, convenciones del equipo, estado del sprint, template de tickets — y escriben desde esa base. Cuanto menos genérico sea tu workspace, más específico y útil es el output.

Cada ticket aprobado alimenta la memoria del sistema. El agente Meta-Observador actualiza el contexto del módulo después de cada ejecución, de modo que tu segundo ticket sobre un módulo es más preciso que el primero, y el décimo más que el quinto.

---

## Inicio rápido

```bash
# 1. Clonar
git clone https://github.com/Dsegovia98/openspired.git
cd openspired

# 2. Un comando: instala + levanta + abre UI
chmod +x openspired && ./openspired
```

> **Opción más barata:** Google Gemini Flash — un pipeline completo de 9 agentes cuesta aproximadamente **$0.01–0.03**.

### Modos del launcher

```bash
./openspired             # default: API + UI web (abre navegador automáticamente)
./openspired --desktop   # API + ventana desktop con Tauri
./openspired --no-open   # útil para sesiones remotas/SSH
```

---

## Cómo funciona

```
Tu requerimiento (lenguaje natural o URL de Jira)
        │
        ▼
  [Orquestador]     clasifica dominio, módulo, tipo de ticket
        │
        ▼
  [Researcher]      agrega contexto del producto e histórico desde workspace
        │
        ▼
  [Dev. Concepto]   construye arquitectura conceptual, anticipa edge cases
        │
        ▼
  [Escritor]        produce ticket estructurado bilingüe EN/ES
        │
        ▼
  [QA + Feedback]   valida formato, detecta gaps, 2–3 flujos críticos
        │
     ── Revisión humana ──  [aprobar / feedback / actualizar template / descartar]
        │
        ▼
  [Documentador]    guarda el ticket en workspace
        │
        ▼
  [Meta-Observador] actualiza contexto del módulo para la próxima ejecución
        │
        ▼
  Tu ticket de Jira  (opcionalmente publicado automáticamente)
```

La revisión humana es donde importa tu criterio. Apruebas, das feedback (el Escritor revisa), o actualizas tu template de tickets — todo antes de que algo toque Jira.

---

## Context Discovery Protocol (CDP)

Los agentes no escriben desde cero. Antes de cada ejecución, el pipeline arma un stack de contexto desde tu workspace:

| Capa | Archivo | Propósito |
|------|---------|-----------|
| 1 | `workspace/modules/{modulo}/context.md` | Estado específico del módulo — qué ya existe, flujos activos, edge cases conocidos |
| 2 | `workspace/context/product_knowledge.md` | Descripción general del producto y mapa de módulos |
| 3 | `workspace/context/sprint_context.md` | Sprint actual, épicas activas |
| 4 | `workspace/context/global.md` | Plataforma, roles, convenciones de formato |
| 5 | `workspace/context/ticket_template.md` | Estructura de tickets de tu equipo (extraída de Jira o definida manualmente) |
| 6 | Definiciones de agentes | Skills e instrucciones específicas de cada agente |

Las capas faltantes degradan de forma elegante — los agentes continúan con lo que hay disponible y documentan sus supuestos. Cada ejecución completa los gaps para la siguiente. Los usuarios nuevos tienen un pipeline funcional desde el minuto uno; los usuarios con experiencia obtienen output cada vez más preciso.

---

## El workspace es tuyo

`workspace/` está en el gitignore y guarda contexto + logs de ejecución. Los tickets generados se guardan en carpetas de dominio en la raíz runtime (por ejemplo `App/` o `Analitica/`), que también están gitignored por defecto en este repo.

```
workspace/
├── context/          # global.md, team.md, product_knowledge.md, sprint_context.md,
│                     # ticket_template.md, preferences.md
│                     # .reasoning_bank/ (patrones, anti-patrones, feedback humano)
├── modules/          # contexto por módulo — actualizado automáticamente por Meta-Observador
└── logs/             # registro de todos los tickets creados

Raíz runtime (gitignored por defecto):
├── App/              # tickets generados del dominio primario (US/DT)
└── Analitica/        # tickets generados del dominio secundario
```

---

## Estructura del proyecto

```
openspired/
├── engine/           # Pipeline Python — config, providers, context builder, TUI
├── agents/           # Definiciones de agentes en Markdown — la capa de inteligencia
│   ├── 00_Orquestador/
│   ├── 01_Documentador/
│   ├── ...
│   └── Workflows/
├── templates/        # Templates de onboarding — se renderizan en workspace/ en el primer run
├── workspace/        # Tu contexto de producto (gitignored)
├── openspired        # Launcher todo-en-uno (API + UI)
├── install.sh        # Instalador legacy de CLI
├── .env.example      # Template de variables de entorno
└── requirements.txt
```

---

## Proveedores de IA

| Proveedor | Modelo | Costo est. / run | Notas |
|-----------|--------|------------------|-------|
| Google | `gemini-2.5-flash-lite` | ~$0.01–0.02 | Recomendado por defecto |
| Google | `gemini-2.5-flash` | ~$0.03–0.05 | Fallback automático en sobrecarga |
| Anthropic | `claude-haiku-4-5` | ~$0.02–0.04 | Alternativa sólida |
| OpenAI | `gpt-4o-mini` | ~$0.02–0.04 | Buena opción |

Configura `PROVIDER` y la API key correspondiente en `.env`. No se requiere ninguna otra configuración.

---

## API local + Desktop (nuevo)

Openspired ahora incluye una capa de API local para integrar UI desktop/web sin cambiar la lógica central del pipeline.

### Iniciar API local (manual/debug)

```bash
python engine/run.py --serve-api
```

Por defecto escucha en `127.0.0.1:8765` y escribe un token de sesión en:

`workspace/logs/.api_token`

### Endpoints API

- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/events` (SSE)
- `POST /runs/{run_id}/review`
- `GET /config/status`
- `POST /setup`
- `GET /artifacts`

### Scaffold desktop

Hay un shell base Tauri + React en `desktop/`:

```bash
cd desktop
npm install
npm run tauri dev
```

La app desktop ahora levanta el backend local automáticamente al abrir.
Para usuario final, ya no se requiere una terminal extra de API.

### Generar instalador macOS (.app + .dmg)

```bash
bash scripts/build-macos-installer.sh
```

Los artefactos quedan en `dist/macos/`.

Release firmado + notarizado:

```bash
# una sola vez: guardar credenciales Apple en perfil de keychain
bash scripts/setup-notary-profile.sh openspired-notary

# en cada release
MACOS_SIGN_IDENTITY="Developer ID Application: TU EMPRESA (TEAMID1234)" \
MACOS_NOTARY_PROFILE="openspired-notary" \
bash scripts/build-macos-installer.sh --notarize
```

---

## Soporte de idiomas

Openspired funciona completamente en **inglés** o **español**. El idioma se selecciona durante el wizard de configuración y se guarda en `workspace/context/preferences.md`. Todos los prompts de UI, archivos generados e instrucciones de agentes se adaptan a tu elección.

El output de los tickets siempre es bilingüe (EN + ES) por defecto — diseñado para equipos multifuncionales.

---

## Para quién es esto

Product managers y diseñadores que quieren pasar menos tiempo estructurando tickets y más en lo que realmente importa: hablar con usuarios, definir problemas y decidir qué construir a continuación.

No necesitas saber programar para usar Openspired. Si puedes ejecutar un comando de terminal y escribir un requerimiento en lenguaje natural, estás listo.

---

## Contribuir

Creemos que el futuro del trabajo de producto está en amplificar el juicio humano, no en reemplazarlo. Si eso resuena, nos encantaría tu ayuda.

Consulta [CONTRIBUTING.md](CONTRIBUTING.md) para comenzar — hay buenos primeros issues para mejoras de agentes, nuevas integraciones y expansiones de idioma.

---

## Licencia

[MIT](LICENSE) — úsalo, forkéalo, construye sobre él. Envía algo bueno.

---

<div align="center">
<sub>Construido por personas de producto que se cansaron de escribir tickets desde cero — y empezaron a preguntarse qué harían con todo ese tiempo de vuelta.</sub>
</div>
