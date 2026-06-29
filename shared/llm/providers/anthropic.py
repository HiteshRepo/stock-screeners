"""
shared.llm.providers.anthropic — Claude via the Anthropic Python SDK.

Install:  pip install anthropic
API key:  set ANTHROPIC_API_KEY environment variable

Docs: https://docs.anthropic.com/en/api
"""
from __future__ import annotations

import os

from ..runner import LLMResponse, LLMRunner

_DEFAULT_SYSTEM = (
    "You are a concise financial analysis assistant helping an individual investor "
    "manage their Indian dividend stock portfolio. Be direct, cite actual numbers "
    "from the data provided, and never fabricate information."
)


class AnthropicRunner(LLMRunner):
    def __init__(self, model: str, api_key: str | None = None):
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for this provider.\n"
                "Install it with:  pip install anthropic"
            ) from exc

        self.model = model
        self._client = _anthropic.Anthropic(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY")
        )

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system or _DEFAULT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return LLMResponse(
            content=msg.content[0].text,
            model=self.model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
        )
