"""
providers/google_prov.py — Proveedor Google Gemini.

El más barato del mercado. Un pipeline completo cuesta ~$0.01-0.03.

Modelos disponibles (Google):
  gemini-2.5-flash-lite       →  $0.075/M input | $0.30/M output  ← RECOMENDADO
  gemini-2.5-flash            →  $0.30/M input  | $1.00/M output
  gemini-2.5-pro              →  $1.25/M input  | $5.00/M output

Conseguir API key (gratis para empezar): https://aistudio.google.com/apikey
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from .base import LLMProvider

# Reintentos ante errores transitorios (503 overload, 429 rate limit)
_RETRYABLE_CODES = {429, 500, 503, 504}
_MAX_RETRIES     = 5
_RETRY_WAIT      = 4.0   # segundos fijos entre reintentos (más simple y predecible)

# Modelo de fallback si el modelo principal está saturado tras todos los reintentos
_FALLBACK_MODEL  = "gemini-2.5-flash"

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _is_overload_error(msg: str) -> bool:
    return any(k in msg for k in ("503", "UNAVAILABLE", "high demand", "429", "RESOURCE_EXHAUSTED"))


class GoogleProvider(LLMProvider):

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "google"

    def call(self, system_prompt: str, user_message: str, model: str, max_tokens: int) -> str:
        return self._call_with_fallback(system_prompt, user_message, model, max_tokens)

    def _call_with_fallback(
        self, system_prompt: str, user_message: str, model: str, max_tokens: int
    ) -> str:
        """Intenta con el modelo principal; si se agota con 503/429, usa el fallback."""
        try:
            return self._call_model(system_prompt, user_message, model, max_tokens)
        except RuntimeError as e:
            if _FALLBACK_MODEL and _FALLBACK_MODEL != model and _is_overload_error(str(e)):
                print(f"\n  🔄 Modelo saturado — usando fallback: {_FALLBACK_MODEL}")
                return self._call_model(system_prompt, user_message, _FALLBACK_MODEL, max_tokens)
            raise

    def _call_model(
        self, system_prompt: str, user_message: str, model: str, max_tokens: int
    ) -> str:
        url = f"{_BASE_URL}/{model}:generateContent?key={self._api_key}"

        payload = json.dumps({
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": user_message}]}
            ],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature":     0.3,
            },
        }).encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(
                url, data=payload,
                headers={"content-type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    candidates = body.get("candidates")
                    if not candidates or not isinstance(candidates, list):
                        raise RuntimeError(f"Google API returned no candidates: {body}")
                    return candidates[0]["content"]["parts"][0]["text"]

            except urllib.error.HTTPError as e:
                code      = e.code
                raw_body  = e.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"Google API {code}: {raw_body}")

                if code in _RETRYABLE_CODES and attempt < _MAX_RETRIES:
                    print(f"\n  ⏳ [{model}] API {code} — reintento {attempt + 1}/{_MAX_RETRIES} en {_RETRY_WAIT:.0f}s...")
                    time.sleep(_RETRY_WAIT)
                    continue

                raise last_error from e

        raise last_error  # type: ignore
