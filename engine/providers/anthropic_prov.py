"""
providers/anthropic_prov.py — Proveedor Anthropic con Prompt Caching y retry.

El prompt caching da un 90% de descuento en tokens de entrada repetidos.
Como el system prompt de cada agente es siempre el mismo entre runs,
el segundo run en adelante paga casi cero en contexto.

Modelos disponibles (Anthropic):
  claude-haiku-4-5-20251001  →  $0.80/M input  | $4/M output   (recomendado)
  claude-sonnet-4-6          →  $3.00/M input  | $15/M output  (para agentes críticos)
  claude-opus-4-6            →  $15.0/M input  | $75/M output  (máxima calidad)
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from .base import LLMProvider, ProviderResponse, ProviderUsage

_API_URL     = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"
_CACHE_BETA  = "prompt-caching-2024-07-31"  # Header para activar prompt caching

# Reintentos ante errores transitorios (429 rate limit, 500/503 overload)
_RETRYABLE_CODES = {429, 500, 503, 504}
_MAX_RETRIES     = 5
_RETRY_WAIT      = 4.0   # segundos entre reintentos


class AnthropicProvider(LLMProvider):

    def __init__(self, api_key: str, use_cache: bool = True):
        self._api_key   = api_key
        self._use_cache = use_cache

    @property
    def name(self) -> str:
        return "anthropic"

    def call(self, system_prompt: str, user_message: str, model: str, max_tokens: int) -> ProviderResponse:
        # Con caching: system prompt como lista con cache_control
        # Sin caching: system prompt como string plano (más compatible)
        if self._use_cache:
            system_field = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_field = system_prompt

        payload = json.dumps({
            "model":      model,
            "max_tokens": max_tokens,
            "system":     system_field,
            "messages":   [{"role": "user", "content": user_message}],
        }).encode("utf-8")

        headers = {
            "x-api-key":         self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type":      "application/json",
        }
        if self._use_cache:
            headers["anthropic-beta"] = _CACHE_BETA

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(_API_URL, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    content = body.get("content")
                    if not content or not isinstance(content, list):
                        raise RuntimeError(f"Anthropic API returned empty content: {body}")
                    usage_data = body.get("usage", {}) if isinstance(body.get("usage", {}), dict) else {}
                    usage = ProviderUsage(
                        input_tokens=int(usage_data.get("input_tokens", 0) or 0),
                        output_tokens=int(usage_data.get("output_tokens", 0) or 0),
                        cache_creation_input_tokens=int(usage_data.get("cache_creation_input_tokens", 0) or 0),
                        cache_read_input_tokens=int(usage_data.get("cache_read_input_tokens", 0) or 0),
                        raw=usage_data,
                    )
                    return ProviderResponse(
                        text=content[0]["text"],
                        usage=usage,
                        provider=self.name,
                        model=model,
                    )

            except urllib.error.HTTPError as e:
                code     = e.code
                raw_body = e.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Anthropic API {code}: {raw_body}")

                if code in _RETRYABLE_CODES and attempt < _MAX_RETRIES:
                    print(f"\n  ⏳ [anthropic/{model}] API {code} — reintento {attempt + 1}/{_MAX_RETRIES} en {_RETRY_WAIT:.0f}s...")
                    time.sleep(_RETRY_WAIT)
                    continue

                raise last_error from e

        raise last_error  # type: ignore
