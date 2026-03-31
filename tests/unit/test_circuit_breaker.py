import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from backend.resilience.circuit_breaker import CircuitBreaker, State

@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.delete = AsyncMock()
    return redis

@pytest.mark.asyncio
async def test_initial_state_closed(mock_redis):
    cb = CircuitBreaker(mock_redis, "test_cb", threshold=3)
    # Mock get_state to return None (defaults to CLOSED)
    mock_redis.get.return_value = None
    state = await cb._get_state()
    assert state == State.CLOSED

@pytest.mark.asyncio
async def test_failure_threshold(mock_redis):
    cb = CircuitBreaker(mock_redis, "test_cb", threshold=2)
    mock_redis.get.return_value = b"closed"
    mock_redis.incr.side_effect = [1, 2] # Two failures
    
    async def failing_func():
        raise ValueError("Fail")
    
    # First failure
    with pytest.raises(ValueError):
        await cb.call(failing_func)
    
    # Second failure - should trip
    with pytest.raises(ValueError):
        await cb.call(failing_func)
    
    # Verify set_state was called with "open"
    # The last set call for state_key should be "open"
    mock_redis.set.assert_any_call("cb:test_cb:state", "open")

@pytest.mark.asyncio
async def test_open_state_raises_exception(mock_redis):
    cb = CircuitBreaker(mock_redis, "test_cb", threshold=3, recovery_timeout=30)
    mock_redis.get.side_effect = [b"open", b"1000000"] # State is OPEN, last_fail is recent
    
    async def some_func():
        return "ok"
    
    with patch("time.time", return_value=1000005): # Only 5 seconds passed
        with pytest.raises(Exception) as exc:
            await cb.call(some_func)
        assert "is OPEN" in str(exc.value)

@pytest.mark.asyncio
async def test_recovery_to_half_open(mock_redis):
    cb = CircuitBreaker(mock_redis, "test_cb", threshold=3, recovery_timeout=30)
    # State OPEN, last_fail is old
    mock_redis.get.side_effect = [b"open", b"1000000"] 
    
    async def success_func():
        return "ok"
    
    with patch("time.time", return_value=1000040): # 40 seconds passed
        res = await cb.call(success_func)
        assert res == "ok"
        # Should have set state to half_open then closed
        mock_redis.set.assert_any_call("cb:test_cb:state", "half_open")
        mock_redis.set.assert_any_call("cb:test_cb:state", "closed")

@pytest.mark.asyncio
async def test_half_open_failure_back_to_open(mock_redis):
    cb = CircuitBreaker(mock_redis, "test_cb", threshold=3, recovery_timeout=30)
    # Simulation of HALF_OPEN failure:
    # 1. call() sees base state is OPEN, check timeout -> moves to HALF_OPEN
    # 2. func() fails -> _handle_failure is called
    mock_redis.get.side_effect = [b"open", b"1000000", b"half_open"]
    mock_redis.incr.return_value = 5 # Above threshold
    
    async def failing_func():
        raise ValueError("Fail")
        
    with patch("time.time", return_value=1000040):
        with pytest.raises(ValueError):
            await cb.call(failing_func)
        mock_redis.set.assert_any_call("cb:test_cb:state", "open")
