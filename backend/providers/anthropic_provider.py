"""
Anthropic Claude LLM provider implementation.

Features:
  - Async client via anthropic.AsyncAnthropic
  - System messages extracted and passed as top-level `system` kwarg
    (Anthropic API convention — system is NOT in the messages list)
  - Per-model price table for cost tracking
  - Streaming via async generator using message stream events
  - embed() raises NotImplementedError (Anthropic has no embedding API)
  - Rate limit retry with exponential backoff
"""

import asyncio
import logging
import time
from typing import AsyncGenerator

from anthropic import AsyncAnthropic, RateLimitError

from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

logger = logging.getLogger(__name__)

# Prices in USD per million tokens
ANTHROPIC_PRICE_TABLE: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    "claude-3-5-haiku-20241022": {"input": 0.80, "output": 4.00},
    "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
}

# Retry configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds


class AnthropicProvider(BaseLLMProvider):
    """Provider implementation for Anthropic Claude models.

    Args:
        api_key: Anthropic API key.
        model: Model identifier (default: "claude-3-5-haiku-20241022").
        max_tokens: Default max output tokens (default: 1024).
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-haiku-20241022",
        max_tokens: int = 1024,
    ):
        self._model = model
        self._max_tokens = max_tokens
        self._client = AsyncAnthropic(api_key=api_key)

        # Resolve pricing from table; default to haiku pricing
        pricing = ANTHROPIC_PRICE_TABLE.get(
            model, ANTHROPIC_PRICE_TABLE["claude-3-5-haiku-20241022"]
        )
        self._cost_per_input_token = pricing["input"] / 1_000_000
        self._cost_per_output_token = pricing["output"] / 1_000_000

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def cost_per_input_token(self) -> float:
        return self._cost_per_input_token

    @property
    def cost_per_output_token(self) -> float:
        return self._cost_per_output_token

    @property
    def context_window(self) -> int:
        """Return context window size for known Claude models."""
        windows = {
            "claude-sonnet-4-20250514": 200_000,
            "claude-3-5-sonnet-20241022": 200_000,
            "claude-3-5-haiku-20241022": 200_000,
            "claude-3-haiku-20240307": 200_000,
            "claude-3-opus-20240229": 200_000,
        }
        return windows.get(self._model, 200_000)

    def _prepare_messages(
        self, messages: list[ChatMessage]
    ) -> tuple[str | None, list[dict]]:
        """Separate system messages from conversation messages.

        Anthropic API requires system messages to be passed as a top-level
        `system` parameter, NOT inside the messages list.

        Args:
            messages: List of ChatMessage objects.

        Returns:
            Tuple of (system_prompt, filtered_messages_list).
        """
        system_parts: list[str] = []
        api_messages: list[dict] = []

        for msg in messages:
            if msg.role == "system":
                # Collect system messages into a single system prompt
                if isinstance(msg.content, str):
                    system_parts.append(msg.content)
                else:
                    # Multi-modal system content — join text parts
                    for part in msg.content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            system_parts.append(part["text"])
                        elif isinstance(part, str):
                            system_parts.append(part)
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        system_prompt = "\n\n".join(system_parts) if system_parts else None
        return system_prompt, api_messages

    async def _retry_with_backoff(self, coro_factory, description: str = "API call"):
        """Execute an async callable with exponential backoff on RateLimitError.

        Args:
            coro_factory: A callable that returns a new coroutine each invocation.
            description: Human-readable label for logging.

        Returns:
            The result of the successful call.

        Raises:
            RateLimitError: After MAX_RETRIES exhausted.
        """
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                return await coro_factory()
            except RateLimitError as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after is None:
                        retry_after = BASE_RETRY_DELAY * (2 ** attempt)
                    logger.warning(
                        f"Rate limited on {description} (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                        f"retrying in {retry_after:.1f}s"
                    )
                    await asyncio.sleep(retry_after)
                else:
                    logger.error(
                        f"Rate limit retries exhausted for {description} after "
                        f"{MAX_RETRIES + 1} attempts"
                    )
                    raise last_error

    async def complete(
        self, messages: list[ChatMessage], **kwargs
    ) -> GenerationResult:
        """Generate a complete response using Anthropic Messages API.

        Args:
            messages: Conversation history.
            **kwargs: Additional params (temperature, max_tokens override, etc.)

        Returns:
            GenerationResult with content and token usage metadata.
        """
        system_prompt, api_messages = self._prepare_messages(messages)
        max_tokens = kwargs.pop("max_tokens", self._max_tokens)
        start_time = time.perf_counter()

        create_kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if system_prompt:
            create_kwargs["system"] = system_prompt

        response = await self._retry_with_backoff(
            lambda: self._client.messages.create(**create_kwargs),
            description=f"complete({self._model})",
        )

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Extract text content from response content blocks
        content_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                content_text += block.text

        cost_usd = self.estimate_cost(
            response.usage.input_tokens, response.usage.output_tokens
        )

        return GenerationResult(
            content=content_text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=round(latency_ms, 2),
            cost_usd=round(cost_usd, 8),
            finish_reason=response.stop_reason or "unknown",
        )

    async def stream(
        self, messages: list[ChatMessage], **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream tokens progressively from Anthropic Messages API.

        Uses the Anthropic streaming interface to yield text deltas
        as they arrive.

        Args:
            messages: Conversation history.
            **kwargs: Additional params.

        Yields:
            Individual token strings as they arrive.
        """
        system_prompt, api_messages = self._prepare_messages(messages)
        max_tokens = kwargs.pop("max_tokens", self._max_tokens)

        create_kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            **kwargs,
        }
        if system_prompt:
            create_kwargs["system"] = system_prompt

        async with self._client.messages.stream(**create_kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Anthropic does not provide an embedding API.

        Raises:
            NotImplementedError: Always. Use OpenAI or another provider for embeddings.
        """
        raise NotImplementedError(
            "Anthropic does not offer an embedding API. "
            "Use OpenAIProvider or another embedding-capable provider."
        )
