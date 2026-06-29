"""
shared.llm.runner — LLM-agnostic runner interface and provider factory.

Design
------
LLMRunner is a thin abstract interface: one method (complete), one return type
(LLMResponse). Provider implementations live in providers/ and are imported
lazily so missing optional dependencies don't break unrelated commands.

Usage
-----
    from shared.llm.runner import create_runner

    runner = create_runner("anthropic", "claude-haiku-4-5-20251001")
    resp   = runner.complete(prompt="Summarise this portfolio…", system="…")
    print(resp.content)

Adding a new provider
---------------------
1. Create shared/llm/providers/<name>.py implementing LLMRunner
2. Add a branch in create_runner()
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMRunner(ABC):
    """Abstract base for all LLM provider implementations."""

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Send *prompt* to the model and return the response."""
        ...


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_SUPPORTED = ("anthropic", "openai", "ollama")


def create_runner(provider: str, model: str, **kwargs) -> LLMRunner:
    """
    Instantiate the correct LLMRunner for *provider*.

    Providers are imported lazily — only the chosen provider's SDK
    needs to be installed.

    Args:
        provider:  "anthropic" | "openai" | "ollama"
        model:     model identifier (e.g. "claude-haiku-4-5-20251001",
                   "gpt-4o-mini", "llama3.1")
        **kwargs:  passed through to the provider constructor
                   (e.g. api_key, ollama_base_url)
    """
    p = provider.lower().strip()

    if p == "anthropic":
        from .providers.anthropic import AnthropicRunner
        return AnthropicRunner(model, **kwargs)

    if p == "openai":
        from .providers.openai import OpenAIRunner
        return OpenAIRunner(model, **kwargs)

    if p == "ollama":
        from .providers.ollama import OllamaRunner
        return OllamaRunner(model, **kwargs)

    raise ValueError(
        f"Unknown provider {provider!r}. "
        f"Supported: {', '.join(_SUPPORTED)}"
    )
