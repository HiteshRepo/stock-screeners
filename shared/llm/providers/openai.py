"""
shared.llm.providers.openai — GPT models via the OpenAI Python SDK.

Install:  pip install openai
API key:  set OPENAI_API_KEY environment variable

Docs: https://platform.openai.com/docs
"""
from __future__ import annotations

import os

from ..runner import LLMResponse, LLMRunner

_DEFAULT_SYSTEM = (
    "You are a concise financial analysis assistant helping an individual investor "
    "manage their Indian dividend stock portfolio. Be direct, cite actual numbers "
    "from the data provided, and never fabricate information."
)


class OpenAIRunner(LLMRunner):
    def __init__(self, model: str, api_key: str | None = None):
        try:
            from openai import OpenAI as _OpenAI
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for this provider.\n"
                "Install it with:  pip install openai"
            ) from exc

        self.model = model
        self._client = _OpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY")
        )

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system or _DEFAULT_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
        )
        usage = resp.usage
        return LLMResponse(
            content=resp.choices[0].message.content or "",
            model=self.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
