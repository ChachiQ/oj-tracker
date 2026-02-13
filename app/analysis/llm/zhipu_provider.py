"""
Zhipu AI (GLM) LLM provider.

Supports GLM-4-Flash and GLM-4-Plus models via the official zhipuai Python SDK.
"""
from __future__ import annotations

import logging
import time

from .base import BaseLLMProvider, LLMResponse
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD)
ZHIPU_PRICING = {
    "glm-4-flash": {"input": 0.07, "output": 0.07},
    "glm-4-plus": {"input": 0.70, "output": 0.70},
}

DEFAULT_MODEL = "glm-4-flash"

try:
    from zhipuai import ZhipuAI

    _ZHIPU_AVAILABLE = True
except ImportError:
    _ZHIPU_AVAILABLE = False
    logger.info(
        "zhipuai package not installed. Zhipu provider will not be available. "
        "Install with: pip install zhipuai"
    )


def _register_if_available(cls):
    """Only register the provider if the zhipuai SDK is importable."""
    if _ZHIPU_AVAILABLE:
        from . import register_provider

        return register_provider(cls)
    return cls


@_register_if_available
class ZhipuProvider(BaseLLMProvider):
    """Zhipu AI (GLM) LLM provider."""

    PROVIDER_NAME = "zhipu"

    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        if _ZHIPU_AVAILABLE and api_key:
            self._client = ZhipuAI(api_key=api_key)
        else:
            self._client = None

    def _ensure_client(self):
        """Lazily initialize the client if not yet created."""
        if self._client is None:
            if not _ZHIPU_AVAILABLE:
                raise RuntimeError(
                    "zhipuai package is not installed. "
                    "Install with: pip install zhipuai"
                )
            if not self.api_key:
                raise ValueError("Zhipu API key is required.")
            from zhipuai import ZhipuAI

            self._client = ZhipuAI(api_key=self.api_key)
        return self._client

    def chat(
        self,
        messages: list,
        model: str = None,
        max_tokens: int = 4096,
        temperature: float = 0,
    ) -> LLMResponse:
        """Send a chat completion request to Zhipu GLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
                      Supports 'system', 'user', and 'assistant' roles.
            model: Model identifier. Defaults to glm-4-flash.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature. Note: Zhipu requires temperature > 0,
                         so 0 is remapped to 0.01.

        Returns:
            LLMResponse with completion result and cost metadata.
        """
        client = self._ensure_client()
        model = model or DEFAULT_MODEL

        # Zhipu API requires temperature > 0
        if temperature <= 0:
            temperature = 0.01

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
        """Return available Zhipu model identifiers."""
        return ["glm-4-flash", "glm-4-plus"]

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
        pricing = ZHIPU_PRICING.get(model, ZHIPU_PRICING[DEFAULT_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)
