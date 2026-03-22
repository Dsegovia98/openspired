"""
providers/base.py — Interfaz común para todos los proveedores de LLM.

Cada proveedor implementa un único método: call(system, user, model, max_tokens) → str
Esto permite cambiar de Anthropic a OpenAI a Google sin tocar el pipeline.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderResponse:
    text: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider: str = ""
    model: str = ""


class LLMProvider(ABC):
    """Interfaz base para cualquier proveedor de LLM."""

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_message:  str,
        model:         str,
        max_tokens:    int,
    ) -> ProviderResponse:
        """
        Hace una llamada aislada al LLM.
        Retorna texto + usage.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del proveedor para logging."""
        ...
