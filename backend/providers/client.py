"""
NeuroFlowClient — singleton async client for LLM provider access.

Features:
  - Holds all provider instances (OpenAI, Anthropic)
  - Exposes client.chat(messages, routing_criteria) and client.embed(texts)
  - Tracks per-model call counts and costs in Redis
  - Emits OpenTelemetry spans for every provider call
  - Integrates with ModelRouter for intelligent model selection
"""

import logging
import time
from collections.abc import AsyncGenerator
from typing import Any, Optional

from opentelemetry import trace
from redis.asyncio import Redis

from backend.config import settings
from backend.providers.anthropic_provider import AnthropicProvider
from backend.providers.base import BaseLLMProvider, ChatMessage, GenerationResult
from backend.providers.openai_provider import OpenAIProvider
from backend.providers.router import (
    FallbackChain,
    ModelConfig,
    ModelRouter,
    RoutingCriteria,
)


logger = logging.getLogger(__name__)
tracer = trace.get_tracer("neuroflow.providers")

# Redis key templates for metrics
CALLS_KEY_TEMPLATE = "metrics:model:{model}:calls"
COST_KEY_TEMPLATE = "metrics:model:{model}:cost_usd"


class NeuroFlowClient:
    """Singleton async client wrapping all LLM provider access.

    Usage:
        client = NeuroFlowClient(redis)
        await client.initialize()

        result = await client.chat(
            messages=[ChatMessage(role="user", content="Hello")],
            routing_criteria=RoutingCriteria(task_type="rag_generation"),
        )

        embeddings = await client.embed(["text to embed"])
    """

    _instance: Optional["NeuroFlowClient"] = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "NeuroFlowClient":
        """Ensure only one instance of NeuroFlowClient exists (singleton)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, redis: Redis | None = None) -> None:
        if self._initialized:
            return
        self._redis = redis
        self._providers: dict[str, BaseLLMProvider] = {}
        self._router: ModelRouter | None = None
        self._fallback_chain: FallbackChain | None = None
        self._initialized = True

    async def initialize(self) -> None:
        """Initialize all provider instances and the model router.

        Reads API keys from config.settings and creates provider instances.
        Must be called once before using chat() or embed().
        """
        # Initialize OpenAI providers
        openai_key = getattr(settings, "OPENAI_API_KEY", None)
        if openai_key:
            self._providers["openai:gpt-4o"] = OpenAIProvider(api_key=openai_key, model="gpt-4o")
            self._providers["openai:gpt-4o-mini"] = OpenAIProvider(
                api_key=openai_key, model="gpt-4o-mini"
            )
            logger.info("Initialized OpenAI providers (gpt-4o, gpt-4o-mini)")
        else:
            logger.warning("OPENAI_API_KEY not set, OpenAI providers unavailable")

        # Initialize Anthropic providers
        anthropic_key = getattr(settings, "ANTHROPIC_API_KEY", None)
        if anthropic_key:
            self._providers["anthropic:claude-3-5-sonnet-20241022"] = AnthropicProvider(
                api_key=anthropic_key, model="claude-3-5-sonnet-20241022"
            )
            self._providers["anthropic:claude-3-5-haiku-20241022"] = AnthropicProvider(
                api_key=anthropic_key, model="claude-3-5-haiku-20241022"
            )
            logger.info("Initialized Anthropic providers (sonnet, haiku)")
        else:
            logger.warning("ANTHROPIC_API_KEY not set, Anthropic providers unavailable")

        # Initialize router
        if self._redis:
            self._router = ModelRouter(self._redis)
            await self._router.load_models()
            logger.info("Model router initialized with Redis")
        else:
            logger.warning("Redis not available, router will use defaults")

        # Build fallback chain with available providers
        fallback_providers = []
        for key, provider in self._providers.items():
            fallback_providers.append((key, provider))
        if fallback_providers:
            self._fallback_chain = FallbackChain(fallback_providers)
            logger.info(f"Fallback chain configured with {len(fallback_providers)} providers")

    def _get_provider(self, config: ModelConfig) -> BaseLLMProvider:
        """Resolve a provider instance from a ModelConfig.

        Args:
            config: The model configuration from the router.

        Returns:
            The matching BaseLLMProvider instance.

        Raises:
            ValueError: If no matching provider is registered.
        """
        key = f"{config.provider}:{config.model_name}"
        if key in self._providers:
            return self._providers[key]

        # Fallback: try to find by provider name (any model from that provider)
        for pkey, provider in self._providers.items():
            if pkey.startswith(config.provider + ":"):
                return provider

        raise ValueError(
            f"No provider registered for {config.provider}:{config.model_name}. "
            f"Available: {list(self._providers.keys())}"
        )

    async def _track_metrics(self, model_name: str, cost_usd: float) -> None:
        """Increment per-model call count and cost in Redis.

        Keys:
          - metrics:model:{model_name}:calls  (incremented by 1)
          - metrics:model:{model_name}:cost_usd  (incremented by cost_usd)
        """
        if not self._redis:
            return
        try:
            calls_key = CALLS_KEY_TEMPLATE.format(model=model_name)
            cost_key = COST_KEY_TEMPLATE.format(model=model_name)

            await self._redis.incr(calls_key)
            await self._redis.incrbyfloat(cost_key, round(cost_usd, 8))
        except Exception as e:
            logger.warning(f"Failed to track metrics in Redis: {e}")

    async def chat(
        self,
        messages: list[ChatMessage],
        routing_criteria: RoutingCriteria | None = None,
        **kwargs: Any,
    ) -> GenerationResult:
        """Send a chat completion request with automatic routing.

        Routes to the optimal provider/model based on criteria, tracks
        metrics in Redis, and emits OpenTelemetry spans.

        Args:
            messages: Conversation history.
            routing_criteria: Criteria for model selection (optional).
            **kwargs: Provider-specific parameters.

        Returns:
            GenerationResult from the selected provider.
        """
        criteria = routing_criteria or RoutingCriteria()

        # Route to the best model
        with tracer.start_as_current_span("neuroflow.chat") as span:
            span.set_attribute("task_type", criteria.task_type)

            try:
                if self._router:
                    config = await self._router.route(criteria)
                    provider = self._get_provider(config)
                    span.set_attribute("model", config.model_name)
                    span.set_attribute("provider", config.provider)
                else:
                    # No router — use first available provider
                    key = next(iter(self._providers))
                    provider = self._providers[key]
                    span.set_attribute("model", provider.model_name)

                start_time = time.perf_counter()
                result = await provider.complete(messages, **kwargs)
                latency_ms = (time.perf_counter() - start_time) * 1000

                # Set span attributes
                span.set_attribute("input_tokens", result.input_tokens)
                span.set_attribute("output_tokens", result.output_tokens)
                span.set_attribute("cost_usd", result.cost_usd)
                span.set_attribute("latency_ms", round(latency_ms, 2))
                span.set_attribute("finish_reason", result.finish_reason)

                # Track metrics in Redis
                await self._track_metrics(result.model, result.cost_usd)

                return result

            except Exception as e:
                span.set_attribute("error", True)
                span.set_attribute("error.message", str(e))

                # Try fallback chain
                if self._fallback_chain:
                    logger.warning(f"Primary provider failed: {e}, trying fallback chain")
                    result = await self._fallback_chain.complete(messages, **kwargs)
                    span.set_attribute("fallback_used", True)
                    span.set_attribute("model", result.model)
                    await self._track_metrics(result.model, result.cost_usd)
                    return result
                raise

    async def stream(
        self,
        messages: list[ChatMessage],
        routing_criteria: RoutingCriteria | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream tokens with automatic routing and telemetry.

        Args:
            messages: Conversation history.
            routing_criteria: Criteria for model selection (optional).
            **kwargs: Provider-specific parameters.

        Yields:
            Individual tokens as strings.
        """
        criteria = routing_criteria or RoutingCriteria()

        with tracer.start_as_current_span("neuroflow.stream") as span:
            span.set_attribute("task_type", criteria.task_type)

            if self._router:
                config = await self._router.route(criteria)
                provider = self._get_provider(config)
                span.set_attribute("model", config.model_name)
                span.set_attribute("provider", config.provider)
            else:
                key = next(iter(self._providers))
                provider = self._providers[key]
                span.set_attribute("model", provider.model_name)

            token_count = 0
            async for token in provider.stream(messages, **kwargs):
                token_count += 1
                yield token

            span.set_attribute("tokens_streamed", token_count)

    async def embed(
        self,
        texts: list[str],
        provider_key: str | None = None,
    ) -> list[list[float]]:
        """Generate embeddings with metrics tracking.

        Uses OpenAI provider by default (Anthropic does not offer embeddings).

        Args:
            texts: List of strings to embed.
            provider_key: Specific provider key to use (e.g. "openai:gpt-4o-mini").

        Returns:
            List of embedding vectors.
        """
        with tracer.start_as_current_span("neuroflow.embed") as span:
            span.set_attribute("num_texts", len(texts))

            # Find an embedding-capable provider
            provider = None
            if provider_key and provider_key in self._providers:
                provider = self._providers[provider_key]
            else:
                # Default to first OpenAI provider (has embedding support)
                for key, p in self._providers.items():
                    if key.startswith("openai:"):
                        provider = p
                        break

            if provider is None:
                raise ValueError(
                    "No embedding-capable provider available. "
                    "Ensure OPENAI_API_KEY is configured."
                )

            span.set_attribute("model", provider.model_name)
            start_time = time.perf_counter()
            embeddings = await provider.embed(texts)
            latency_ms = (time.perf_counter() - start_time) * 1000

            span.set_attribute("latency_ms", round(latency_ms, 2))
            span.set_attribute("num_embeddings", len(embeddings))

            # Track embedding calls
            await self._track_metrics(provider.model_name, 0.0)

            return embeddings

    async def get_metrics(self, model_name: str) -> dict[str, Any]:
        """Retrieve tracked metrics for a specific model from Redis.

        Args:
            model_name: The model identifier.

        Returns:
            Dict with 'calls' and 'cost_usd' values.
        """
        if not self._redis:
            return {"calls": 0, "cost_usd": 0.0}

        calls_key = CALLS_KEY_TEMPLATE.format(model=model_name)
        cost_key = COST_KEY_TEMPLATE.format(model=model_name)

        calls = await self._redis.get(calls_key)
        cost = await self._redis.get(cost_key)

        return {
            "calls": int(calls) if calls else 0,
            "cost_usd": float(cost) if cost else 0.0,
        }

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (useful for testing)."""
        cls._instance = None
