# ADR 0001 — API-First Local Core

## Context
Openspired tenía lógica de negocio acoplada al flujo CLI/TUI interactivo, lo que dificultaba una app desktop y automatización UI sin terminal.

## Decision
Adoptar arquitectura API-first local:
- `pipeline` y servicios de negocio quedan en Python como source of truth.
- Exponer casos de uso por API local (`127.0.0.1`) con SSE para progreso en vivo.
- CLI/TUI consumen el mismo core y conservan compatibilidad.

## Consequences
- Se habilita desktop/web local sin duplicar lógica.
- Se centraliza validación y manejo de estados.
- Se requiere capa de seguridad local (token + loopback).
