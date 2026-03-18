"""
providers/openai_prov.py — Proveedor OpenAI con retry.

Modelos disponibles (OpenAI):
  gpt-4o-mini   →  $0.15/M input | $0.60/M output  (muy recomendado — relación calidad/precio)
  gpt-4o        →  $2.50/M input | $10/M output
  o1-mini       →  $1.10/M input | $4.40/M output
  o3-mini       →  $1.10/M input | $4.40/M output

Conseguir API key: https://platform.openai.com/api-keys
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from .base import LLMProvider

_API_URL = "https://api.openai.com/v1/chat/completions"

# Reintentos ante errores transitorios (429 rate limit, 500/503 overload)
_RETRYABLE_CODES = {429, 500, 503, 504}
_MAX_RETRIES     = 5
_RETRY_WAIT      = 4.0   # segundos entre reintentos


class OpenAIProvider(LLMProvider):

    def __init__(self, api_key: str):
        self._api_key = api_key

    @property
    def name(self) -> str:
        return "openai"

    def call(self, system_prompt: str, user_message: str, model: str, max_tokens: int) -> str:
        payload = json.dumps({
            "model":      model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        }).encode("utf-8")

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type":  "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            req = urllib.request.Request(_API_URL, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    choices = body.get("choices")
                    if not choices or not isinstance(choices, list):
                        raise RuntimeError(f"OpenAI API returned empty choices: {body}")
                    return choices[0]["message"]["content"]

            except urllib.error.HTTPError as e:
                code     = e.code
                raw_body = e.read().decode("utf-8", errors="replace")
                last_error = RuntimeError(f"OpenAI API {code}: {raw_body}")

                if code in _RETRYABLE_CODES and attempt < _MAX_RETRIES:
                    print(f"\n  ⏳ [openai/{model}] API {code} — reintento {attempt + 1}/{_MAX_RETRIES} en {_RETRY_WAIT:.0f}s...")
                    time.sleep(_RETRY_WAIT)
                    continue

                raise last_error from e

        raise last_error  # type: ignore
