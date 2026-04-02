"""
OpenAI / OpenAI-compatible LLM provider implementation.

Features:
  - Async client via openai.AsyncOpenAI
  - Hardcoded per-model price table for cost tracking
  - Streaming via async generator
  - Batch embedding with text-embedding-3-small (batch size 100)
  - Rate limit retry with exponential backoff (up to 3 retries)
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from backend.providers.base import BaseLLMProvider, ChatMessage, GenerationResult

logger = logging.getLogger(__name__)

# Prices in USD per million tokens
OPENAI_PRICE_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_BATCH_SIZE = 100

# Retry configuration
MAX_RETRIES = 3
BASE_RETRY_DELAY = 1.0  # seconds


class OpenAIProvider(BaseLLMProvider):
    """Provider implementation for OpenAI and OpenAI-compatible APIs.

    Args:
        api_key: OpenAI API key.
        model: Model identifier (default: "gpt-4o-mini").
        base_url: Optional base URL for OpenAI-compatible APIs.
        embedding_model: Model to use for embeddings.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str | None = None,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

        # Resolve pricing from table; default to gpt-4o-mini pricing
        pricing = OPENAI_PRICE_TABLE.get(model, OPENAI_PRICE_TABLE["gpt-4o-mini"])
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
        """Return context window size for known models."""
        windows = {
            "gpt-4o": 128_000,
            "gpt-4o-mini": 128_000,
            "gpt-4-turbo": 128_000,
            "gpt-4": 8_192,
            "gpt-3.5-turbo": 16_385,
        }
        return windows.get(self._model, 128_000)

    def _format_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """Convert ChatMessage list to OpenAI API format."""
        formatted = []
        for msg in messages:
            formatted.append({"role": msg.role, "content": msg.content})
        return formatted

    async def _retry_with_backoff(
        self, coro_factory: Callable[[], Any], description: str = "API call"
    ) -> Any:  # noqa: ANN401
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
                    # Use retry_after from the error if available
                    retry_after = getattr(e, "retry_after", None)
                    if retry_after is None:
                        retry_after = BASE_RETRY_DELAY * (2**attempt)
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

    async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> GenerationResult:  # noqa: ANN401
        """Generate a complete response using OpenAI chat completions.

        Args:
            messages: Conversation history.
            **kwargs: Additional params forwarded to the API (temperature, max_tokens, etc.)

        Returns:
            GenerationResult with content and token usage metadata.
        """
        formatted = self._format_messages(messages)
        start_time = time.perf_counter()

        response = await self._retry_with_backoff(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=formatted,
                **kwargs,
            ),
            description=f"complete({self._model})",
        )

        latency_ms = (time.perf_counter() - start_time) * 1000
        choice = response.choices[0]
        usage = response.usage

        cost_usd = self.estimate_cost(usage.prompt_tokens, usage.completion_tokens)

        return GenerationResult(
            content=choice.message.content or "",
            model=response.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            latency_ms=round(latency_ms, 2),
            cost_usd=round(cost_usd, 8),
            finish_reason=choice.finish_reason or "unknown",
        )

    async def stream(self, messages: list[ChatMessage], **kwargs: Any) -> AsyncGenerator[str, None]:  # noqa: ANN401
        """Stream tokens progressively from OpenAI chat completions.

        Args:
            messages: Conversation history.
            **kwargs: Additional params forwarded to the API.

        Yields:
            Individual token strings as they arrive.
        """
        formatted = self._format_messages(messages)

        response_stream = await self._retry_with_backoff(
            lambda: self._client.chat.completions.create(
                model=self._model,
                messages=formatted,
                stream=True,
                **kwargs,
            ),
            description=f"stream({self._model})",
        )

        async for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using text-embedding-3-small in batches of 100.

        Args:
            texts: List of strings to embed.

        Returns:
            List of embedding vectors.
        """
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            response = await self._retry_with_backoff(
                lambda b=batch: self._client.embeddings.create(
                    model=self._embedding_model,
                    input=b,
                ),
                description=f"embed(batch {i // EMBEDDING_BATCH_SIZE + 1})",
            )
            # Sort by index to preserve order
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])

        return all_embeddings
