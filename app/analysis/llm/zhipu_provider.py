"""
Zhipu AI (GLM) LLM provider.

Supports GLM-5 model via the official zhipuai Python SDK.
"""
from __future__ import annotations

import logging
import time

from .base import BaseLLMProvider, LLMResponse
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD)
ZHIPU_PRICING = {
    "glm-5": {"input": 1.0, "output": 3.2},
}

DEFAULT_MODEL = "glm-5"

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
            model: Model identifier. Defaults to glm-5.
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

        # Extract content — reasoning models may swap content/reasoning_content
        choice = response.choices[0]
        content = choice.message.content or ""
        reasoning = getattr(choice.message, 'reasoning_content', None) or ""
        if content and reasoning:
            c_stripped = content.strip()
            r_stripped = reasoning.strip()
            content_looks_json = c_stripped.startswith('{') or c_stripped.startswith('```')
            reasoning_looks_json = r_stripped.startswith('{') or r_stripped.startswith('```')
            if not content_looks_json and reasoning_looks_json:
                logger.info(f"Zhipu: swapping content/reasoning_content (reasoning has JSON, {len(reasoning)} chars)")
                content = reasoning
        elif not content and reasoning:
            logger.info(f"Zhipu: content empty, using reasoning_content ({len(reasoning)} chars)")
            content = reasoning

        logger.info(
            f"Zhipu LLM response: model={model}, "
            f"finish_reason={choice.finish_reason}, "
            f"content_len={len(content)}, "
            f"latency={latency_ms}ms"
        )
        if not content or choice.finish_reason != "stop":
            logger.warning(
                f"Zhipu unexpected response: finish_reason={choice.finish_reason}, "
                f"content_len={len(content)}, model={model}, "
                f"message={choice.message}"
            )

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
        return ["glm-5"]

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
