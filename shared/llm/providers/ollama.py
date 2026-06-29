"""
shared.llm.providers.ollama — local models via the Ollama REST API.

Install:  https://ollama.com  (no Python package needed — uses requests)
Run:      ollama serve
Pull:     ollama pull llama3.1

The Ollama API is OpenAI-compatible; we use the /api/generate endpoint
for simplicity (no streaming).

Docs: https://github.com/ollama/ollama/blob/main/docs/api.md
"""
from __future__ import annotations

import requests

from ..runner import LLMResponse, LLMRunner

_DEFAULT_BASE_URL = "http://localhost:11434"


class OllamaRunner(LLMRunner):
    def __init__(
        self,
        model: str,
        ollama_base_url: str = _DEFAULT_BASE_URL,
    ):
        self.model = model
        self.base_url = ollama_base_url.rstrip("/")

    def complete(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 1000,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Could not connect to Ollama at {self.base_url}. "
                "Is `ollama serve` running?"
            ) from exc

        data = resp.json()
        return LLMResponse(
            content=data.get("response", ""),
            model=self.model,
            # Ollama doesn't return token counts in /api/generate by default
            input_tokens=data.get("prompt_eval_count"),
            output_tokens=data.get("eval_count"),
        )
