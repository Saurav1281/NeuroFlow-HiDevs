"""
Model router with intelligent routing and fallback chain.

The ModelRouter selects the optimal provider+model given routing criteria.
Model configurations are stored in Redis (key: router:models) and updated
when fine-tuning jobs complete.

FallbackChain provides reliability by trying providers in order when
one fails with a non-retryable error.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

from redis.asyncio import Redis

from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

logger = logging.getLogger(__name__)

# Default estimated tokens per call for cost filtering
DEFAULT_ESTIMATED_INPUT_TOKENS = 1000
DEFAULT_ESTIMATED_OUTPUT_TOKENS = 500


@dataclass
class RoutingCriteria:
    """Criteria for selecting the right provider and model.

    Attributes:
        task_type: The type of task being performed.
            One of "rag_generation", "evaluation", "embedding", "classification".
        max_cost_per_call: Maximum cost in USD allowed for a single call.
        require_vision: Whether the model must support vision/image inputs.
        require_long_context: Whether the model needs >32k token context.
        latency_budget_ms: Maximum acceptable latency in milliseconds.
        prefer_fine_tuned: Whether to prefer a fine-tuned model for this task_type.
    """
    task_type: str = "rag_generation"
    max_cost_per_call: float | None = None
    require_vision: bool = False
    require_long_context: bool = False
    latency_budget_ms: int | None = None
    prefer_fine_tuned: bool = False


@dataclass
class ModelConfig:
    """Configuration for a registered model.

    This is the schema expected in the Redis router:models list.

    Attributes:
        provider: Provider name ("openai" or "anthropic").
        model_name: Model identifier (e.g. "gpt-4o-mini").
        supports_vision: Whether this model supports image inputs.
        context_window: Max context window in tokens.
        cost_per_input_token: Cost in USD per input token.
        cost_per_output_token: Cost in USD per output token.
        is_fine_tuned: Whether this is a fine-tuned model.
        fine_tuned_task_types: Task types this fine-tuned model is optimized for.
        is_judge_model: Whether this model is suitable as an evaluation judge.
        avg_latency_ms: Average latency in milliseconds (for latency filtering).
    """
    provider: str
    model_name: str
    supports_vision: bool = False
    context_window: int = 128_000
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0
    is_fine_tuned: bool = False
    fine_tuned_task_types: list[str] = field(default_factory=list)
    is_judge_model: bool = False
    avg_latency_ms: int = 1000

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        """Create a ModelConfig from a dictionary."""
        return cls(
            provider=data.get("provider", "openai"),
            model_name=data.get("model_name", ""),
            supports_vision=data.get("supports_vision", False),
            context_window=data.get("context_window", 128_000),
            cost_per_input_token=data.get("cost_per_input_token", 0.0),
            cost_per_output_token=data.get("cost_per_output_token", 0.0),
            is_fine_tuned=data.get("is_fine_tuned", False),
            fine_tuned_task_types=data.get("fine_tuned_task_types", []),
            is_judge_model=data.get("is_judge_model", False),
            avg_latency_ms=data.get("avg_latency_ms", 1000),
        )


# Default model registry used when Redis is empty or unavailable
DEFAULT_MODEL_CONFIGS: list[dict] = [
    {
        "provider": "openai",
        "model_name": "gpt-4o",
        "supports_vision": True,
        "context_window": 128_000,
        "cost_per_input_token": 2.50 / 1_000_000,
        "cost_per_output_token": 10.00 / 1_000_000,
        "is_fine_tuned": False,
        "fine_tuned_task_types": [],
        "is_judge_model": True,
        "avg_latency_ms": 2000,
    },
    {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "supports_vision": True,
        "context_window": 128_000,
        "cost_per_input_token": 0.15 / 1_000_000,
        "cost_per_output_token": 0.60 / 1_000_000,
        "is_fine_tuned": False,
        "fine_tuned_task_types": [],
        "is_judge_model": False,
        "avg_latency_ms": 800,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-3-5-sonnet-20241022",
        "supports_vision": True,
        "context_window": 200_000,
        "cost_per_input_token": 3.00 / 1_000_000,
        "cost_per_output_token": 15.00 / 1_000_000,
        "is_fine_tuned": False,
        "fine_tuned_task_types": [],
        "is_judge_model": True,
        "avg_latency_ms": 1500,
    },
    {
        "provider": "anthropic",
        "model_name": "claude-3-5-haiku-20241022",
        "supports_vision": False,
        "context_window": 200_000,
        "cost_per_input_token": 0.80 / 1_000_000,
        "cost_per_output_token": 4.00 / 1_000_000,
        "is_fine_tuned": False,
        "fine_tuned_task_types": [],
        "is_judge_model": False,
        "avg_latency_ms": 600,
    },
]


class ModelRouter:
    """Selects the optimal provider and model based on routing criteria.

    The router reads model configs from Redis (key: router:models) and
    applies the following rules in order:

    1. require_vision=True → filter to vision-capable models
    2. require_long_context=True → filter to models with >100k context
    3. prefer_fine_tuned=True AND fine-tuned exists for task_type → use it
    4. task_type="evaluation" → always use a judge model, never fine-tuned
    5. max_cost_per_call set → filter by estimated cost
    6. latency_budget_ms set → filter by average latency
    7. Default: cheapest model satisfying all hard constraints

    Args:
        redis: Async Redis connection for reading model configs.
    """

    REDIS_KEY = "router:models"

    def __init__(self, redis: Redis):
        self._redis = redis
        self._model_configs: list[ModelConfig] = []
        self._loaded = False

    async def load_models(self) -> None:
        """Load model configurations from Redis.

        Falls back to DEFAULT_MODEL_CONFIGS if Redis key is empty or unavailable.
        """
        try:
            raw = await self._redis.get(self.REDIS_KEY)
            if raw:
                configs_data = json.loads(raw)
                self._model_configs = [
                    ModelConfig.from_dict(cfg) for cfg in configs_data
                ]
                logger.info(
                    f"Loaded {len(self._model_configs)} models from Redis"
                )
            else:
                self._model_configs = [
                    ModelConfig.from_dict(cfg) for cfg in DEFAULT_MODEL_CONFIGS
                ]
                logger.info(
                    "No models in Redis, using default model configs"
                )
        except Exception as e:
            logger.warning(f"Failed to load models from Redis: {e}, using defaults")
            self._model_configs = [
                ModelConfig.from_dict(cfg) for cfg in DEFAULT_MODEL_CONFIGS
            ]
        self._loaded = True

    async def _ensure_loaded(self) -> None:
        """Ensure model configs are loaded before routing."""
        if not self._loaded:
            await self.load_models()

    async def route(self, criteria: RoutingCriteria) -> ModelConfig:
        """Select the best model based on the given criteria.

        Applies all routing rules and returns the optimal ModelConfig.

        Args:
            criteria: RoutingCriteria specifying task requirements.

        Returns:
            The selected ModelConfig.

        Raises:
            ValueError: If no model satisfies all constraints.
        """
        await self._ensure_loaded()

        candidates = list(self._model_configs)

        # RULE 1: Vision requirement
        if criteria.require_vision:
            candidates = [c for c in candidates if c.supports_vision]
            if not candidates:
                raise ValueError("No vision-capable models available")

        # RULE 2: Long context requirement (>100k tokens)
        if criteria.require_long_context:
            candidates = [c for c in candidates if c.context_window > 100_000]
            if not candidates:
                raise ValueError("No long-context models available (>100k tokens)")

        # RULE 3: Evaluation task → must use judge model, never fine-tuned
        if criteria.task_type == "evaluation":
            candidates = [
                c for c in candidates if c.is_judge_model and not c.is_fine_tuned
            ]
            if not candidates:
                raise ValueError("No suitable judge models available for evaluation")

        # RULE 4: Prefer fine-tuned for this task_type
        elif criteria.prefer_fine_tuned:
            fine_tuned = [
                c for c in candidates
                if c.is_fine_tuned and criteria.task_type in c.fine_tuned_task_types
            ]
            if fine_tuned:
                candidates = fine_tuned

        # RULE 5: Cost filtering
        if criteria.max_cost_per_call is not None:
            candidates = [
                c for c in candidates
                if self._estimate_call_cost(c) <= criteria.max_cost_per_call
            ]
            if not candidates:
                raise ValueError(
                    f"No models available within cost budget "
                    f"${criteria.max_cost_per_call:.6f}"
                )

        # RULE 6: Latency budget filtering
        if criteria.latency_budget_ms is not None:
            candidates = [
                c for c in candidates
                if c.avg_latency_ms <= criteria.latency_budget_ms
            ]
            if not candidates:
                raise ValueError(
                    f"No models available within latency budget "
                    f"{criteria.latency_budget_ms}ms"
                )

        # RULE 7: Default — pick cheapest model
        candidates.sort(
            key=lambda c: (
                c.cost_per_input_token * DEFAULT_ESTIMATED_INPUT_TOKENS
                + c.cost_per_output_token * DEFAULT_ESTIMATED_OUTPUT_TOKENS
            )
        )

        selected = candidates[0]
        logger.info(
            f"Routed task_type={criteria.task_type} → "
            f"{selected.provider}/{selected.model_name}"
        )
        return selected

    @staticmethod
    def _estimate_call_cost(config: ModelConfig) -> float:
        """Estimate cost for a typical call using default token estimates."""
        return (
            config.cost_per_input_token * DEFAULT_ESTIMATED_INPUT_TOKENS
            + config.cost_per_output_token * DEFAULT_ESTIMATED_OUTPUT_TOKENS
        )


class FallbackChain:
    """Tries providers in order if one fails with a non-retryable error.

    This is a real-world reliability pattern used when a single provider
    has an outage. For example: [gpt-4o-mini, claude-haiku, gpt-4o].

    Args:
        providers: Ordered list of (name, provider) tuples to try.
    """

    # Errors that should NOT trigger fallback (caller should handle)
    RETRYABLE_ERROR_TYPES = (
        ConnectionError,
        TimeoutError,
    )

    def __init__(self, providers: list[tuple[str, BaseLLMProvider]]):
        if not providers:
            raise ValueError("FallbackChain requires at least one provider")
        self._providers = providers

    async def complete(
        self, messages: list[ChatMessage], **kwargs
    ) -> GenerationResult:
        """Try each provider in order until one succeeds.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific parameters.

        Returns:
            GenerationResult from the first successful provider.

        Raises:
            Exception: The last error if all providers fail.
        """
        last_error: Exception | None = None

        for name, provider in self._providers:
            try:
                result = await provider.complete(messages, **kwargs)
                logger.info(f"FallbackChain: succeeded with provider '{name}'")
                return result
            except Exception as e:
                last_error = e
                logger.warning(
                    f"FallbackChain: provider '{name}' failed with "
                    f"{type(e).__name__}: {e}, trying next..."
                )
                continue

        raise last_error  # type: ignore[misc]

    async def stream(
        self, messages: list[ChatMessage], **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream tokens with fallback — tries each provider in order.

        If a provider fails during the initial stream setup,
        falls back to the next provider in the chain.

        Args:
            messages: Conversation history.
            **kwargs: Provider-specific parameters.

        Yields:
            Individual token strings from the first successful provider.

        Raises:
            Exception: If all providers fail.
        """
        last_error: Exception | None = None

        for name, provider in self._providers:
            try:
                logger.info(f"FallbackChain: trying provider '{name}' for streaming")
                async for token in provider.stream(messages, **kwargs):
                    yield token
                # If we successfully streamed, we're done
                logger.info(f"FallbackChain: streaming succeeded with provider '{name}'")
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    f"FallbackChain: provider '{name}' stream failed with "
                    f"{type(e).__name__}: {e}, trying next..."
                )
                continue

        if last_error:
            raise last_error
        raise RuntimeError("No providers available in FallbackChain")

