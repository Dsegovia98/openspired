# Skill: Navegación Fractal para Mapeo de Interfaz
## Agente: Mapeador de Interfaz
## Cuándo usar: Siempre — es la habilidad core del Mapeador.

---

## Protocolo de Navegación Fractal

La navegación fractal significa: entras a cada sección, abres cada pestaña, cada dropdown, cada modal de "Configurar" o "Crear", observas su contenido en modo lectura, y cierras antes de continuar. Nunca saltes a la siguiente pantalla sin haber agotado los sub-elementos de la actual.

---

## Secuencia de ejecución

### Paso 0 — Preparación
1. Pide al PO que confirme: "¿Estás logueado y el navegador está listo en la URL de entrada?"
2. Lee `workspace/context/interface_map.md` para ver qué ya existe. No borres secciones ya documentadas.
3. Si el PO proporcionó una plantilla de navegación (con las áreas/módulos a explorar), léela para priorizar. Si no hay plantilla, navega el menú principal y construye el mapa desde cero.

### Paso 1 — Tomar control del navegador
- Toma un screenshot inicial de la URL de entrada.
- Identifica el menú de navegación principal: ¿barra lateral, barra superior, tabs?
- Lista mentalmente las secciones visibles. Estas serán las **Áreas** del interface_map.

### Paso 2 — Exploración fractal por Área
Para cada Área del menú principal:
1. Navega a esa sección (click en el ítem del menú).
2. Toma screenshot.
3. Identifica los **Módulos** dentro del Área (sub-menús, tabs, cards principales).
4. Para cada Módulo: navega → toma screenshot → identifica pantallas.

### Paso 3 — Mapeo de cada Pantalla
Para cada pantalla que encuentres, documenta:

```
- Nombre de la pantalla: [el nombre que aparece en el título o breadcrumb]
- Estados que observas:
  * Estado principal: [descripción de la vista con datos]
  * Estado vacío: [si existe, qué CTA o mensaje muestra]
  * Estado de carga: [spinner, skeleton, etc.]
  * Estado de error: [si es visible]
- Acciones disponibles:
  * FULL: [lista de botones/acciones que ves: Crear, Editar, Eliminar, Exportar, etc.]
  * BASIC: [¿hay diferencia visible de permisos? ¿algunos botones están deshabilitados o ausentes?]
- Columnas / campos visibles: [si es una tabla, lista los headers]
- Modales/formularios: [si hay un botón de "Crear" o "Configurar", ábrelo, toma screenshot del formulario con sus campos, cierra con Cancelar]
```

### Paso 4 — Explorar estados alternativos
Cuando encuentres una tabla o lista:
- Busca filtros y documenta cuáles existen (no los uses — solo observa los labels).
- Busca tabs dentro del módulo — cada tab es una pantalla separada.
- Busca el estado vacío: ¿qué pasa si no hay datos?

### Paso 5 — Modales y paneles de detalle
- Abre modales de "Crear" o "Configurar" para ver los campos del formulario.
- **NUNCA rellenes campos reales.** Solo observa y toma screenshot.
- Cierra siempre con "Cancelar" o la X.
- Documenta: nombre del modal, campos que contiene, validaciones visibles, botón de acción.

---

## Formato de output

Produce o actualiza `workspace/context/interface_map.md` siguiendo esta estructura:

```markdown
## [ÁREA] — Ej: Administración

### [Módulo] — Ej: Usuarios
- **[Nombre de Pantalla]**
  - Estados: [Normal (descripción)] | [Vacío (descripción, CTA si existe)] | [Cargando]
  - Acceso: BASIC ([qué puede hacer]) | FULL ([qué puede hacer adicionalmente])
  - Descripción: [Qué hace esta pantalla. Columnas de tabla si aplica. Acciones principales.]
  - Modal "[Nombre del modal]": Campos: [campo1, campo2, ...]. Acción: [Guardar/Crear/etc.]

- **[Nombre de Pantalla 2]**
  - ...
```

---

## Reglas de oro

1. **Nombres reales:** Usa el texto exacto que aparece en la UI (el nombre del botón, el título del modal, el breadcrumb). No inventes nombres.
2. **Un estado por observación:** Solo documenta estados que realmente viste. Si no viste el estado vacío, escribe `(no observado)`.
3. **BASIC vs FULL:** Si no puedes distinguir los roles visualmente (porque estás logueado como FULL), documenta las acciones que ves y agrega `(verificar restricciones BASIC)`.
4. **Pantallas no exploradas:** Si sabes que existe una sección pero no la navegaste, agrégala como `- **[Nombre]** (pendiente de exploración)`.
5. **Nunca rompas el mapa existente:** Si `interface_map.md` ya tiene secciones documentadas, agrégalas/completa — no las sobreescribas.
