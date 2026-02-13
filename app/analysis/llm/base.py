"""
Base classes for LLM providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    latency_ms: int = 0


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers.

    All provider implementations must subclass this and implement
    the required abstract methods.
    """

    PROVIDER_NAME: str = ""

    def __init__(self, api_key: str = None):
        self.api_key = api_key

    @abstractmethod
    def chat(
        self,
        messages: list,
        model: str = None,
        max_tokens: int = 4096,
        temperature: float = 0,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model identifier. If None, uses provider default.
            max_tokens: Maximum tokens in the response.
            temperature: Sampling temperature (0 = deterministic).

        Returns:
            LLMResponse with the completion result and metadata.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        """Return a list of available model identifiers for this provider."""
        ...

    @abstractmethod
    def estimate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Estimate the cost in USD for the given token counts.

        Args:
            input_tokens: Number of input/prompt tokens.
            output_tokens: Number of output/completion tokens.
            model: Model identifier for pricing lookup.

        Returns:
            Estimated cost in USD.
        """
        ...
