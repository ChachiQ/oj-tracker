"""
Anthropic Claude LLM provider.

Supports Claude Haiku 4.5 and Claude Opus 4.6 models via the
official anthropic Python SDK.
"""
from __future__ import annotations

import logging
import time

from .base import BaseLLMProvider, LLMResponse
from .config import MODEL_CONFIG

logger = logging.getLogger(__name__)

# Pricing per million tokens (USD)
CLAUDE_PRICING = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
}

DEFAULT_MODEL = "claude-haiku-4-5"

try:
    import anthropic

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    logger.info(
        "anthropic package not installed. Claude provider will not be available. "
        "Install with: pip install anthropic"
    )


def _register_if_available(cls):
    """Only register the provider if the anthropic SDK is importable."""
    if _ANTHROPIC_AVAILABLE:
        from . import register_provider

        return register_provider(cls)
    return cls


@_register_if_available
class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude LLM provider."""

    PROVIDER_NAME = "claude"

    def __init__(self, api_key: str = None):
        super().__init__(api_key=api_key)
        if _ANTHROPIC_AVAILABLE and api_key:
            self._client = anthropic.Anthropic(api_key=api_key, timeout=600.0)
        else:
            self._client = None

    def _ensure_client(self):
        """Lazily initialize the client if not yet created."""
        if self._client is None:
            if not _ANTHROPIC_AVAILABLE:
                raise RuntimeError(
                    "anthropic package is not installed. "
                    "Install with: pip install anthropic"
                )
            if not self.api_key:
                raise ValueError("Anthropic API key is required.")
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=600.0)
        return self._client

    def chat(
        self,
        messages: list,
        model: str = None,
        max_tokens: int = 4096,
        temperature: float = 0,
    ) -> LLMResponse:
        """Send a chat completion request to Claude.

        Args:
            messages: List of message dicts. Claude uses 'user' and 'assistant' roles.
                      If a 'system' role message is present, it is extracted and passed
                      as the system parameter.
            model: Model identifier. Defaults to claude-haiku-4-5.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            LLMResponse with completion result and cost metadata.
        """
        client = self._ensure_client()
        model = model or DEFAULT_MODEL

        # Extract system message if present
        system_message = None
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg["content"]
            else:
                chat_messages.append(msg)

        # Build request kwargs
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": chat_messages,
            "temperature": temperature,
        }
        if system_message:
            kwargs["system"] = system_message

        start_time = time.time()
        response = client.messages.create(**kwargs)
        latency_ms = int((time.time() - start_time) * 1000)

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = self.estimate_cost(input_tokens, output_tokens, model)

        return LLMResponse(
            content=content,
            model=model,
            provider=self.PROVIDER_NAME,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason or "",
        )

    def list_models(self) -> list[str]:
        """Return available Claude model identifiers."""
        return ["claude-haiku-4-5", "claude-opus-4-6"]

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
        pricing = CLAUDE_PRICING.get(model, CLAUDE_PRICING[DEFAULT_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        return round(input_cost + output_cost, 6)
