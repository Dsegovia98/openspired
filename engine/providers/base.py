"""
providers/base.py — Interfaz común para todos los proveedores de LLM.

Cada proveedor implementa un único método: call(system, user, model, max_tokens) → str
Esto permite cambiar de Anthropic a OpenAI a Google sin tocar el pipeline.
"""
from __future__ import annotations
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interfaz base para cualquier proveedor de LLM."""

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_message:  str,
        model:         str,
        max_tokens:    int,
    ) -> str:
        """
        Hace una llamada aislada al LLM.
        Retorna el texto de respuesta limpio.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre del proveedor para logging."""
        ...
