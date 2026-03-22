"""
utils/costs.py — Token/cost estimation helpers.

Prices are approximate USD per 1M tokens and should be updated when provider
pricing changes.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pricing:
    input_per_million: float
    output_per_million: float


# Approximate list used by setup/provider docs in this repo.
_PRICING: dict[tuple[str, str], Pricing] = {
    # Anthropic
    ("anthropic", "claude-haiku-4-5-20251001"): Pricing(0.80, 4.00),
    ("anthropic", "claude-sonnet-4-6"): Pricing(3.00, 15.00),
    ("anthropic", "claude-opus-4-6"): Pricing(15.00, 75.00),
    # OpenAI
    ("openai", "gpt-4o-mini"): Pricing(0.15, 0.60),
    ("openai", "gpt-4o"): Pricing(2.50, 10.00),
    ("openai", "o1-mini"): Pricing(1.10, 4.40),
    ("openai", "o3-mini"): Pricing(1.10, 4.40),
    # Google
    ("google", "gemini-2.5-flash-lite"): Pricing(0.075, 0.30),
    ("google", "gemini-2.5-flash"): Pricing(0.30, 1.00),
    ("google", "gemini-2.5-pro"): Pricing(1.25, 5.00),
}


def _fallback_key(provider: str, model: str) -> tuple[str, str] | None:
    p = provider.lower().strip()
    m = model.lower().strip()

    # Provider-specific soft matching to avoid missing cost when model IDs vary.
    if p == "google":
        if "flash-lite" in m:
            return (p, "gemini-2.5-flash-lite")
        if "flash" in m:
            return (p, "gemini-2.5-flash")
        if "pro" in m:
            return (p, "gemini-2.5-pro")
    if p == "openai":
        if "gpt-4o-mini" in m:
            return (p, "gpt-4o-mini")
        if "gpt-4o" in m:
            return (p, "gpt-4o")
        if "o1-mini" in m:
            return (p, "o1-mini")
        if "o3-mini" in m:
            return (p, "o3-mini")
    if p == "anthropic":
        if "haiku" in m:
            return (p, "claude-haiku-4-5-20251001")
        if "sonnet" in m:
            return (p, "claude-sonnet-4-6")
        if "opus" in m:
            return (p, "claude-opus-4-6")
    return None


def resolve_pricing(provider: str, model: str) -> Pricing | None:
    key = (provider.lower().strip(), model.strip())
    if key in _PRICING:
        return _PRICING[key]
    fb = _fallback_key(provider, model)
    if fb:
        return _PRICING.get(fb)
    return None


def estimate_cost_usd(
    provider: str,
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    """
    Returns estimated USD cost for a model call.

    For Anthropic prompt caching, cached reads are billed at ~10% input cost.
    If pricing is unknown, returns 0.0.
    """
    pricing = resolve_pricing(provider, model)
    if not pricing:
        return 0.0

    in_tokens = max(0, int(input_tokens))
    out_tokens = max(0, int(output_tokens))
    cache_read = max(0, int(cache_read_input_tokens))
    cache_creation = max(0, int(cache_creation_input_tokens))

    billable_input = in_tokens + cache_creation + int(cache_read * 0.1)
    return (billable_input / 1_000_000.0) * pricing.input_per_million + (out_tokens / 1_000_000.0) * pricing.output_per_million
