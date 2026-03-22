# CLI No-Regression Gate

## Objetivo
Asegurar paridad funcional al introducir core/API para desktop.

## Checklist
- [ ] `python engine/run.py --check` mantiene validaciones clave.
- [ ] `python engine/run.py "..."` sigue ejecutando pipeline manual.
- [ ] `python engine/run.py --jira KEY-123` mantiene flujo Jira origen/destino.
- [ ] Revisión humana en CLI conserva `approve/feedback/discard`.
- [ ] Errores de API key/Jira siguen siendo accionables.
- [ ] Paths de salida permanecen dentro de `RUNTIME_PROJECT_ROOT`.
- [ ] Registro de tickets en `_Registro.md` sigue consistente.
