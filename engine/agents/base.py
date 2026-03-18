"""
agents/base.py — Runner aislado de agente con soporte multi-proveedor.

Cada llamada a run_agent() es una conversación completamente nueva con el LLM.
Sin memoria compartida. Sin historial. Solo system_prompt + user_message.

El proveedor (Anthropic / OpenAI / Google) se configura en .env via PROVIDER=...
El modelo por agente se configura via MODEL_<AGENTE>=... en .env
"""
from __future__ import annotations
import asyncio
import threading
from typing import Optional
import config
from providers.base import LLMProvider

# ─── Singleton del proveedor activo ──────────────────────────────────────────
# El Lock garantiza que dos coroutines paralelas (ej: ideador + researcher)
# nunca creen dos instancias simultáneas del provider. Thread-safe.
_provider: Optional[LLMProvider] = None
_provider_lock = threading.Lock()


def _get_provider() -> LLMProvider:
    """Instancia (una sola vez) el proveedor configurado en .env. Thread-safe."""
    global _provider
    # Fast-path: si ya está inicializado no adquirimos el lock
    if _provider is not None:
        return _provider

    with _provider_lock:
        # Double-checked locking: otro thread puede haberlo creado mientras esperábamos
        if _provider is not None:
            return _provider

        p = config.PROVIDER
        if p == "anthropic":
            from providers.anthropic_prov import AnthropicProvider
            _provider = AnthropicProvider(
                api_key=config.ANTHROPIC_API_KEY,
                use_cache=config.USE_CACHE,
            )
        elif p == "openai":
            from providers.openai_prov import OpenAIProvider
            _provider = OpenAIProvider(api_key=config.OPENAI_API_KEY)
        elif p == "google":
            from providers.google_prov import GoogleProvider
            _provider = GoogleProvider(api_key=config.GOOGLE_API_KEY)
        else:
            raise ValueError(
                f"Proveedor desconocido: '{p}'. "
                "Opciones válidas: anthropic | openai | google"
            )
    return _provider


def run_agent(
    agent_name:    str,
    system_prompt: str,
    user_message:  str,
    max_tokens:    int = config.MAX_TOKENS,
) -> str:
    """
    Ejecuta un agente en un contexto completamente aislado.
    Usa el modelo específico de ese agente (o DEFAULT_MODEL si no tiene override).
    """
    model    = config.AGENT_MODELS.get(agent_name, config.DEFAULT_MODEL)
    provider = _get_provider()
    return provider.call(system_prompt, user_message, model, max_tokens)


async def run_agent_async(
    agent_name:    str,
    system_prompt: str,
    user_message:  str,
    max_tokens:    int = config.MAX_TOKENS,
) -> str:
    """
    Versión async — permite ejecución paralela con asyncio.gather().
    Corre la llamada en un thread separado para no bloquear el event loop.
    """
    return await asyncio.to_thread(
        run_agent,
        agent_name,
        system_prompt,
        user_message,
        max_tokens,
    )
