"""
Abstract base interface for all LLM providers.

Every provider must implement the full BaseLLMProvider contract:
  - complete()  → single-shot generation
  - stream()    → progressive token streaming
  - embed()     → text embedding
  - cost & context properties
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator
from dataclasses import dataclass, field


@dataclass
class ChatMessage:
    """Represents a single message in a conversation.

    Attributes:
        role: One of "system", "user", or "assistant".
        content: A string for text-only messages, or a list of dicts
                 for multi-modal content (e.g. images + text).
    """
    role: str   # "system" | "user" | "assistant"
    content: str | list  # str for text, list for multi-modal


@dataclass
class GenerationResult:
    """Encapsulates the result of a single LLM generation call.

    Attributes:
        content: The generated text.
        model: Model identifier used for this generation.
        input_tokens: Number of input (prompt) tokens consumed.
        output_tokens: Number of output (completion) tokens generated.
        latency_ms: Wall-clock latency of the call in milliseconds.
        cost_usd: Estimated cost in USD based on token counts.
        finish_reason: Why generation stopped (e.g. "stop", "length", "tool_calls").
    """
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_usd: float
    finish_reason: str


class BaseLLMProvider(ABC):
    """Abstract base class that every LLM provider must implement.

    This ensures NeuroFlow is never locked to a single provider.
    Concrete implementations must provide:
      - complete():  Non-streaming completion
      - stream():    Async generator yielding tokens
      - embed():     Batch text embedding
      - Cost properties for budget-aware routing
      - context_window for context-length routing
    """

    @abstractmethod
    async def complete(
        self, messages: list[ChatMessage], **kwargs
    ) -> GenerationResult:
        """Generate a complete response for the given messages.

        Args:
            messages: Conversation history as a list of ChatMessage.
            **kwargs: Provider-specific parameters (temperature, max_tokens, etc.)

        Returns:
            GenerationResult with the generated content and metadata.
        """
        ...

    @abstractmethod
    async def stream(
        self, messages: list[ChatMessage], **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream tokens progressively for the given messages.

        Args:
            messages: Conversation history as a list of ChatMessage.
            **kwargs: Provider-specific parameters.

        Yields:
            Individual tokens or token chunks as strings.
        """
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors (list of floats) corresponding
            to each input text.
        """
        ...

    @property
    @abstractmethod
    def cost_per_input_token(self) -> float:
        """Cost in USD per single input token."""
        ...

    @property
    @abstractmethod
    def cost_per_output_token(self) -> float:
        """Cost in USD per single output token."""
        ...

    @property
    @abstractmethod
    def context_window(self) -> int:
        """Maximum context window size in tokens."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The identifier of the model this provider wraps."""
        ...

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost for a call with the given token counts.

        Args:
            input_tokens: Expected number of input tokens.
            output_tokens: Expected number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        return (
            input_tokens * self.cost_per_input_token
            + output_tokens * self.cost_per_output_token
        )
