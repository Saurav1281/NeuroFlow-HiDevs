"""
Standalone test script for the LLM Provider Abstraction Layer.

Tests cover:
  1. Both providers implement the full BaseLLMProvider interface (isinstance checks)
  2. Rate limit retry logic works — mocking a 429 response
  3. ModelRouter correctly routes vision queries to vision-capable models
  4. ModelRouter routes evaluation tasks to judge models
  5. ModelRouter routes to cheapest model by default
  6. ModelRouter respects max_cost_per_call filtering
  7. ModelRouter prefers fine-tuned models when requested
  8. FallbackChain tries providers in order when one fails
  9. NeuroFlowClient singleton pattern works
  10. Cost estimation is correct
  11. Streaming yields tokens progressively (mock-based)
  12. Embedding batches correctly (mock-based)

Usage:
  cd backend && python test_provider.py
"""

import asyncio
import json
import sys
import time
import logging
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from dataclasses import dataclass

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Track test results
passed = 0
failed = 0
total = 0


def test_result(name: str, success: bool, detail: str = ""):
    """Record and print a test result."""
    global passed, failed, total
    total += 1
    if success:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


# ─────────────────────────────────────────────────────────
# TEST 1: Interface compliance
# ─────────────────────────────────────────────────────────
def test_interface_compliance():
    """Both providers implement the full BaseLLMProvider interface."""
    print("\n[Test 1] Interface Compliance")
    from providers.base import BaseLLMProvider
    from providers.openai_provider import OpenAIProvider
    from providers.anthropic_provider import AnthropicProvider

    # OpenAI provider
    provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini")
    test_result(
        "OpenAIProvider is BaseLLMProvider",
        isinstance(provider, BaseLLMProvider),
    )

    # Check all abstract methods exist
    for method_name in ["complete", "stream", "embed"]:
        test_result(
            f"OpenAIProvider has {method_name}()",
            hasattr(provider, method_name) and callable(getattr(provider, method_name)),
        )

    for prop_name in ["cost_per_input_token", "cost_per_output_token", "context_window", "model_name"]:
        test_result(
            f"OpenAIProvider has {prop_name} property",
            hasattr(provider, prop_name),
        )

    # Anthropic provider
    provider2 = AnthropicProvider(api_key="test-key", model="claude-3-5-haiku-20241022")
    test_result(
        "AnthropicProvider is BaseLLMProvider",
        isinstance(provider2, BaseLLMProvider),
    )

    for method_name in ["complete", "stream", "embed"]:
        test_result(
            f"AnthropicProvider has {method_name}()",
            hasattr(provider2, method_name) and callable(getattr(provider2, method_name)),
        )

    for prop_name in ["cost_per_input_token", "cost_per_output_token", "context_window", "model_name"]:
        test_result(
            f"AnthropicProvider has {prop_name} property",
            hasattr(provider2, prop_name),
        )


# ─────────────────────────────────────────────────────────
# TEST 2: Cost properties are correct
# ─────────────────────────────────────────────────────────
def test_cost_properties():
    """Cost properties match expected price table values."""
    print("\n[Test 2] Cost Properties")
    from providers.openai_provider import OpenAIProvider
    from providers.anthropic_provider import AnthropicProvider

    # gpt-4o-mini: input=0.15/M, output=0.60/M
    oai = OpenAIProvider(api_key="test", model="gpt-4o-mini")
    expected_input = 0.15 / 1_000_000
    expected_output = 0.60 / 1_000_000
    test_result(
        "gpt-4o-mini input cost",
        abs(oai.cost_per_input_token - expected_input) < 1e-12,
        f"got {oai.cost_per_input_token}, expected {expected_input}",
    )
    test_result(
        "gpt-4o-mini output cost",
        abs(oai.cost_per_output_token - expected_output) < 1e-12,
        f"got {oai.cost_per_output_token}, expected {expected_output}",
    )
    test_result(
        "gpt-4o-mini context window",
        oai.context_window == 128_000,
        f"got {oai.context_window}",
    )

    # claude-3-5-haiku: input=0.80/M, output=4.00/M
    ant = AnthropicProvider(api_key="test", model="claude-3-5-haiku-20241022")
    expected_input_ant = 0.80 / 1_000_000
    expected_output_ant = 4.00 / 1_000_000
    test_result(
        "claude-haiku input cost",
        abs(ant.cost_per_input_token - expected_input_ant) < 1e-12,
        f"got {ant.cost_per_input_token}, expected {expected_input_ant}",
    )
    test_result(
        "claude-haiku output cost",
        abs(ant.cost_per_output_token - expected_output_ant) < 1e-12,
        f"got {ant.cost_per_output_token}, expected {expected_output_ant}",
    )
    test_result(
        "claude-haiku context window",
        ant.context_window == 200_000,
        f"got {ant.context_window}",
    )


# ─────────────────────────────────────────────────────────
# TEST 3: Cost estimation
# ─────────────────────────────────────────────────────────
def test_cost_estimation():
    """estimate_cost() calculates correctly."""
    print("\n[Test 3] Cost Estimation")
    from providers.openai_provider import OpenAIProvider

    oai = OpenAIProvider(api_key="test", model="gpt-4o")
    # gpt-4o: input=2.50/M, output=10.00/M
    cost = oai.estimate_cost(1000, 500)
    expected = (1000 * 2.50 / 1_000_000) + (500 * 10.00 / 1_000_000)
    test_result(
        "estimate_cost(1000, 500) for gpt-4o",
        abs(cost - expected) < 1e-10,
        f"got {cost}, expected {expected}",
    )


# ─────────────────────────────────────────────────────────
# TEST 4: Rate limit retry logic
# ─────────────────────────────────────────────────────────
def test_rate_limit_retry():
    """Rate limit retry with exponential backoff works correctly."""
    print("\n[Test 4] Rate Limit Retry Logic")

    async def _test():
        from providers.openai_provider import OpenAIProvider, RateLimitError

        provider = OpenAIProvider(api_key="test-key", model="gpt-4o-mini")
        call_count = 0

        # Create a mock response for the successful call
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 10
        mock_usage.completion_tokens = 5

        mock_choice = MagicMock()
        mock_choice.message.content = "Hello"
        mock_choice.finish_reason = "stop"

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.usage = mock_usage
        mock_response.model = "gpt-4o-mini"

        # Create a rate limit error that looks realistic
        mock_http_response = MagicMock()
        mock_http_response.status_code = 429
        mock_http_response.headers = {"retry-after": "0.01"}

        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_http_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise rate_limit_error
            return mock_response

        provider._client.chat.completions.create = mock_create

        from providers.base import ChatMessage
        messages = [ChatMessage(role="user", content="Hello")]

        start = time.perf_counter()
        result = await provider.complete(messages)
        elapsed = time.perf_counter() - start

        test_result(
            "Retried on 429 and eventually succeeded",
            result.content == "Hello",
            f"got content: {result.content}",
        )
        test_result(
            "Made 3 total calls (2 failures + 1 success)",
            call_count == 3,
            f"call_count={call_count}",
        )
        test_result(
            "Retry delays were applied (total > 0s)",
            elapsed > 0,
            f"elapsed={elapsed:.3f}s",
        )

        # Test exhausted retries
        call_count_2 = 0

        async def mock_always_fail(**kwargs):
            nonlocal call_count_2
            call_count_2 += 1
            raise rate_limit_error

        provider._client.chat.completions.create = mock_always_fail

        try:
            await provider.complete(messages)
            test_result("Raises after max retries", False, "Did not raise")
        except RateLimitError:
            test_result("Raises RateLimitError after max retries", True)
        test_result(
            "Made 4 total attempts (initial + 3 retries)",
            call_count_2 == 4,
            f"call_count_2={call_count_2}",
        )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 5: Anthropic system message handling
# ─────────────────────────────────────────────────────────
def test_anthropic_system_messages():
    """System messages are extracted as top-level param, not in messages list."""
    print("\n[Test 5] Anthropic System Message Handling")
    from providers.anthropic_provider import AnthropicProvider
    from providers.base import ChatMessage

    provider = AnthropicProvider(api_key="test-key")

    messages = [
        ChatMessage(role="system", content="You are a helpful assistant."),
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi there!"),
        ChatMessage(role="system", content="Be concise."),
        ChatMessage(role="user", content="What is 2+2?"),
    ]

    system_prompt, api_messages = provider._prepare_messages(messages)

    test_result(
        "System messages extracted",
        system_prompt == "You are a helpful assistant.\n\nBe concise.",
        f"got: {system_prompt}",
    )
    test_result(
        "No system messages in api_messages",
        all(m["role"] != "system" for m in api_messages),
    )
    test_result(
        "Correct number of non-system messages",
        len(api_messages) == 3,
        f"got {len(api_messages)}",
    )


# ─────────────────────────────────────────────────────────
# TEST 6: Anthropic embed raises NotImplementedError
# ─────────────────────────────────────────────────────────
def test_anthropic_embed_not_implemented():
    """Anthropic embed() raises NotImplementedError."""
    print("\n[Test 6] Anthropic Embed NotImplementedError")
    from providers.anthropic_provider import AnthropicProvider

    async def _test():
        provider = AnthropicProvider(api_key="test-key")
        try:
            await provider.embed(["hello"])
            test_result("embed() raises NotImplementedError", False, "Did not raise")
        except NotImplementedError:
            test_result("embed() raises NotImplementedError", True)

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 7: ModelRouter routing rules
# ─────────────────────────────────────────────────────────
def test_model_router():
    """ModelRouter applies all routing rules correctly."""
    print("\n[Test 7] ModelRouter Routing Rules")

    async def _test():
        from providers.router import ModelRouter, RoutingCriteria, ModelConfig

        # Create a mock Redis
        mock_redis = AsyncMock()

        # Set up model configs in Redis
        model_configs = [
            {
                "provider": "openai",
                "model_name": "gpt-4o",
                "supports_vision": True,
                "context_window": 128_000,
                "cost_per_input_token": 2.50 / 1_000_000,
                "cost_per_output_token": 10.00 / 1_000_000,
                "is_fine_tuned": False,
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
                "is_judge_model": False,
                "avg_latency_ms": 600,
            },
            {
                "provider": "openai",
                "model_name": "ft:gpt-4o-mini:rag",
                "supports_vision": False,
                "context_window": 128_000,
                "cost_per_input_token": 0.30 / 1_000_000,
                "cost_per_output_token": 1.20 / 1_000_000,
                "is_fine_tuned": True,
                "fine_tuned_task_types": ["rag_generation"],
                "is_judge_model": False,
                "avg_latency_ms": 900,
            },
        ]

        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        router = ModelRouter(mock_redis)

        # TEST 7a: Vision routing → must pick a vision-capable model
        config = await router.route(RoutingCriteria(require_vision=True))
        test_result(
            "Vision query routes to vision-capable model",
            config.supports_vision,
            f"got {config.model_name} (vision={config.supports_vision})",
        )

        # TEST 7b: Long context → must have >100k tokens
        router._loaded = False  # force reload
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(RoutingCriteria(require_long_context=True))
        test_result(
            "Long context routes to >100k model",
            config.context_window > 100_000,
            f"got {config.model_name} (context={config.context_window})",
        )

        # TEST 7c: Evaluation → must use judge model, never fine-tuned
        router._loaded = False
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(RoutingCriteria(task_type="evaluation"))
        test_result(
            "Evaluation routes to judge model",
            config.is_judge_model,
            f"got {config.model_name} (judge={config.is_judge_model})",
        )
        test_result(
            "Evaluation never uses fine-tuned model",
            not config.is_fine_tuned,
            f"got {config.model_name} (fine_tuned={config.is_fine_tuned})",
        )

        # TEST 7d: Prefer fine-tuned for rag_generation
        router._loaded = False
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(
            RoutingCriteria(task_type="rag_generation", prefer_fine_tuned=True)
        )
        test_result(
            "Prefer fine-tuned routes to fine-tuned model for rag_generation",
            config.is_fine_tuned and "rag_generation" in config.fine_tuned_task_types,
            f"got {config.model_name} (fine_tuned={config.is_fine_tuned})",
        )

        # TEST 7e: Default → cheapest model
        router._loaded = False
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(RoutingCriteria(task_type="classification"))
        test_result(
            "Default routes to cheapest model (gpt-4o-mini)",
            config.model_name == "gpt-4o-mini",
            f"got {config.model_name}",
        )

        # TEST 7f: Cost filtering
        router._loaded = False
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(
            RoutingCriteria(max_cost_per_call=0.001)
        )
        estimated_cost = (
            config.cost_per_input_token * 1000
            + config.cost_per_output_token * 500
        )
        test_result(
            "Cost filter respects max_cost_per_call",
            estimated_cost <= 0.001,
            f"got {config.model_name} (est. cost={estimated_cost:.6f})",
        )

        # TEST 7g: Latency budget filtering
        router._loaded = False
        mock_redis.get = AsyncMock(return_value=json.dumps(model_configs))
        config = await router.route(
            RoutingCriteria(latency_budget_ms=1000)
        )
        test_result(
            "Latency budget routes to fast model",
            config.avg_latency_ms <= 1000,
            f"got {config.model_name} (latency={config.avg_latency_ms}ms)",
        )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 8: FallbackChain
# ─────────────────────────────────────────────────────────
def test_fallback_chain():
    """FallbackChain tries providers in order when one fails."""
    print("\n[Test 8] FallbackChain")

    async def _test():
        from providers.router import FallbackChain
        from providers.base import BaseLLMProvider, ChatMessage, GenerationResult

        # Create mock providers
        failing_provider = AsyncMock(spec=BaseLLMProvider)
        failing_provider.complete = AsyncMock(
            side_effect=Exception("Provider 1 is down")
        )

        success_result = GenerationResult(
            content="Hello from fallback",
            model="fallback-model",
            input_tokens=10,
            output_tokens=5,
            latency_ms=100.0,
            cost_usd=0.001,
            finish_reason="stop",
        )
        success_provider = AsyncMock(spec=BaseLLMProvider)
        success_provider.complete = AsyncMock(return_value=success_result)

        chain = FallbackChain([
            ("primary", failing_provider),
            ("fallback", success_provider),
        ])

        messages = [ChatMessage(role="user", content="Hello")]
        result = await chain.complete(messages)

        test_result(
            "FallbackChain uses second provider when first fails",
            result.content == "Hello from fallback",
            f"got: {result.content}",
        )
        test_result(
            "Primary provider was called",
            failing_provider.complete.called,
        )
        test_result(
            "Fallback provider was called",
            success_provider.complete.called,
        )

        # Test all providers fail
        failing2 = AsyncMock(spec=BaseLLMProvider)
        failing2.complete = AsyncMock(
            side_effect=Exception("Provider 2 also down")
        )

        chain2 = FallbackChain([
            ("p1", failing_provider),
            ("p2", failing2),
        ])

        try:
            await chain2.complete(messages)
            test_result("Raises when all providers fail", False, "Did not raise")
        except Exception as e:
            test_result(
                "Raises last error when all providers fail",
                "Provider 2 also down" in str(e),
                f"got: {e}",
            )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 9: NeuroFlowClient singleton
# ─────────────────────────────────────────────────────────
def test_client_singleton():
    """NeuroFlowClient is a singleton."""
    print("\n[Test 9] NeuroFlowClient Singleton")
    from providers.client import NeuroFlowClient

    # Reset singleton for clean test
    NeuroFlowClient.reset()

    c1 = NeuroFlowClient()
    c2 = NeuroFlowClient()
    test_result(
        "Same instance returned",
        c1 is c2,
    )

    # Clean up
    NeuroFlowClient.reset()


# ─────────────────────────────────────────────────────────
# TEST 10: Redis metrics tracking
# ─────────────────────────────────────────────────────────
def test_redis_metrics():
    """Client tracks call counts and costs in Redis."""
    print("\n[Test 10] Redis Metrics Tracking")

    async def _test():
        from providers.client import NeuroFlowClient

        NeuroFlowClient.reset()
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock()
        mock_redis.incrbyfloat = AsyncMock()

        client = NeuroFlowClient(redis=mock_redis)
        await client._track_metrics("gpt-4o-mini", 0.0005)

        test_result(
            "Redis incr called for call count",
            mock_redis.incr.called,
        )
        test_result(
            "Redis incrbyfloat called for cost",
            mock_redis.incrbyfloat.called,
        )

        # Check the keys used
        calls_key = mock_redis.incr.call_args[0][0]
        cost_key = mock_redis.incrbyfloat.call_args[0][0]
        test_result(
            "Correct calls key format",
            calls_key == "metrics:model:gpt-4o-mini:calls",
            f"got: {calls_key}",
        )
        test_result(
            "Correct cost key format",
            cost_key == "metrics:model:gpt-4o-mini:cost_usd",
            f"got: {cost_key}",
        )

        NeuroFlowClient.reset()

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 11: ModelRouter uses Redis key
# ─────────────────────────────────────────────────────────
def test_router_redis_key():
    """ModelRouter reads from correct Redis key."""
    print("\n[Test 11] ModelRouter Redis Key")

    async def _test():
        from providers.router import ModelRouter

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)  # empty

        router = ModelRouter(mock_redis)
        await router.load_models()

        # Check it tried to read from the correct key
        mock_redis.get.assert_called_with("router:models")
        test_result(
            "Router reads from 'router:models' key",
            True,
        )

        # Check fallback to defaults when key is empty
        test_result(
            "Falls back to default configs when key is empty",
            len(router._model_configs) > 0,
            f"got {len(router._model_configs)} configs",
        )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 12: OpenAI message formatting
# ─────────────────────────────────────────────────────────
def test_openai_message_formatting():
    """OpenAI provider formats messages correctly."""
    print("\n[Test 12] OpenAI Message Formatting")
    from providers.openai_provider import OpenAIProvider
    from providers.base import ChatMessage

    provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")

    messages = [
        ChatMessage(role="system", content="Be helpful"),
        ChatMessage(role="user", content="Hello"),
        ChatMessage(role="assistant", content="Hi!"),
    ]

    formatted = provider._format_messages(messages)

    test_result(
        "Correct number of formatted messages",
        len(formatted) == 3,
        f"got {len(formatted)}",
    )
    test_result(
        "System message included in OpenAI format",
        formatted[0] == {"role": "system", "content": "Be helpful"},
        f"got {formatted[0]}",
    )
    test_result(
        "User message formatted correctly",
        formatted[1] == {"role": "user", "content": "Hello"},
    )


# ─────────────────────────────────────────────────────────
# TEST 13: Streaming yields tokens (mock)
# ─────────────────────────────────────────────────────────
def test_streaming_mock():
    """stream() yields tokens progressively."""
    print("\n[Test 13] Streaming Yields Tokens (Mock)")

    async def _test():
        from providers.openai_provider import OpenAIProvider
        from providers.base import ChatMessage

        provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")

        # Create mock streaming chunks
        chunks = []
        for token in ["Hello", " ", "World", "!"]:
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta.content = token
            chunks.append(chunk)

        # Add final chunk with no content
        final_chunk = MagicMock()
        final_chunk.choices = [MagicMock()]
        final_chunk.choices[0].delta.content = None
        chunks.append(final_chunk)

        # Create async iterator
        async def mock_stream():
            for chunk in chunks:
                yield chunk

        # Mock the create method to return our async generator
        async def mock_create(**kwargs):
            return mock_stream()

        provider._client.chat.completions.create = mock_create

        messages = [ChatMessage(role="user", content="Say hello world")]
        tokens = []
        async for token in provider.stream(messages):
            tokens.append(token)
            print(f"    Token: '{token}'", end="", flush=True)
        print()  # newline after tokens

        test_result(
            "Received all tokens",
            len(tokens) == 4,
            f"got {len(tokens)} tokens: {tokens}",
        )
        test_result(
            "Tokens are correct",
            "".join(tokens) == "Hello World!",
            f"got: {''.join(tokens)}",
        )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 14: Embedding batching (mock)
# ─────────────────────────────────────────────────────────
def test_embedding_batching():
    """embed() batches texts in groups of 100."""
    print("\n[Test 14] Embedding Batching (Mock)")

    async def _test():
        from providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(api_key="test", model="gpt-4o-mini")
        call_count = 0

        async def mock_embed_create(**kwargs):
            nonlocal call_count
            call_count += 1
            texts = kwargs.get("input", [])
            data = []
            for i, _ in enumerate(texts):
                item = MagicMock()
                item.index = i
                item.embedding = [0.1] * 10  # mock 10-dim embedding
                data.append(item)
            response = MagicMock()
            response.data = data
            return response

        provider._client.embeddings.create = mock_embed_create

        # Test with 150 texts (should make 2 batches: 100 + 50)
        texts = [f"text {i}" for i in range(150)]
        embeddings = await provider.embed(texts)

        test_result(
            "Correct number of embeddings returned",
            len(embeddings) == 150,
            f"got {len(embeddings)}",
        )
        test_result(
            "Made 2 batch calls (100 + 50)",
            call_count == 2,
            f"call_count={call_count}",
        )
        test_result(
            "Each embedding has correct dimension",
            all(len(e) == 10 for e in embeddings),
        )

    asyncio.run(_test())


# ─────────────────────────────────────────────────────────
# TEST 15: FallbackChain requires at least one provider
# ─────────────────────────────────────────────────────────
def test_fallback_chain_validation():
    """FallbackChain raises ValueError with empty provider list."""
    print("\n[Test 15] FallbackChain Validation")
    from providers.router import FallbackChain

    try:
        FallbackChain([])
        test_result("Raises ValueError for empty chain", False, "Did not raise")
    except ValueError:
        test_result("Raises ValueError for empty chain", True)


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("NeuroFlow LLM Provider Abstraction Layer — Test Suite")
    print("=" * 60)

    test_interface_compliance()
    test_cost_properties()
    test_cost_estimation()
    test_rate_limit_retry()
    test_anthropic_system_messages()
    test_anthropic_embed_not_implemented()
    test_model_router()
    test_fallback_chain()
    test_client_singleton()
    test_redis_metrics()
    test_router_redis_key()
    test_openai_message_formatting()
    test_streaming_mock()
    test_embedding_batching()
    test_fallback_chain_validation()

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
