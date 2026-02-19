"""
OpenAI LLM provider.

Supports GPT-4.1-mini and GPT-5.2 models via the official openai Python SDK.
"""
from __future__ import annotations

import logging
import time

from .base import BaseLLMProvider, LLMResponse
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD)
OPENAI_PRICING = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-5.2": {"input": 1.75, "output": 14.0},
}

DEFAULT_MODEL = "gpt-4.1-mini"

try:
    import openai

    _OPENAI_AVAILABLE = True
except ImportError:
    _OPENAI_AVAILABLE = False
    logger.info(
        "openai package not installed. OpenAI provider will not be available. "
        "Install with: pip install openai"
    )


def _register_if_available(cls):
    """Only register the provider if the openai SDK is importable."""
    if _OPENAI_AVAILABLE:
        from . import register_provider

        return register_provider(cls)
    return cls


@_register_if_available
class OpenAIProvider(BaseLLMProvider):
    """OpenAI GPT LLM provider."""

    PROVIDER_NAME = "openai"

    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        if _OPENAI_AVAILABLE and api_key:
            self._client = openai.OpenAI(api_key=api_key, timeout=600.0)
        else:
            self._client = None

    def _ensure_client(self):
        """Lazily initialize the client if not yet created."""
        if self._client is None:
            if not _OPENAI_AVAILABLE:
                raise RuntimeError(
                    "openai package is not installed. "
                    "Install with: pip install openai"
                )
            if not self.api_key:
                raise ValueError("OpenAI API key is required.")
            self._client = openai.OpenAI(api_key=self.api_key, timeout=600.0)
        return self._client

    def chat(
        self,
        messages: list,
        model: str = None,
        max_tokens: int = 4096,
        temperature: float = 0,
    ) -> LLMResponse:
        """Send a chat completion request to OpenAI.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Supports 'system', 'user', and 'assistant' roles.
            model: Model identifier. Defaults to gpt-4.1-mini.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            LLMResponse with completion result and cost metadata.
        """
        client = self._ensure_client()
        model = model or DEFAULT_MODEL

        start_time = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Extract content
        choice = response.choices[0]
        content = choice.message.content or ""

        input_tokens = response.usage.prompt_tokens if response.usage else 0
        output_tokens = response.usage.completion_tokens if response.usage else 0
        cost = self.estimate_cost(input_tokens, output_tokens, model)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.PROVIDER_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
        )

    def list_models(self) -> list[str]:
        """Return available OpenAI model identifiers."""
        return ["gpt-4.1-mini", "gpt-5.2"]

    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Estimate cost in USD for the given token counts.

        Args:
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            model: Model identifier for pricing lookup.

        Returns:
            Estimated cost in USD.
        """
        pricing = OPENAI_PRICING.get(model, OPENAI_PRICING[DEFAULT_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)
