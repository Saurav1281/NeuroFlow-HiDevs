import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Any, Optional
from redis.asyncio import Redis

from backend.monitoring.metrics import circuit_breaker_trips, active_circuit_breakers_open

logger = logging.getLogger(__name__)

class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    """Redis-backed async circuit breaker for distributed resilience."""
    
    def __init__(
        self, 
        redis: Redis, 
        name: str, 
        threshold: int = 5, 
        recovery_timeout: int = 30
    ):
        self.redis = redis
        self.name = f"cb:{name}"
        self.provider = name # Store provider name for metrics
        self.threshold = threshold
        self.recovery_timeout = recovery_timeout
        self._state_key = f"{self.name}:state"
        self._fail_count_key = f"{self.name}:fail_count"
        self._last_fail_time_key = f"{self.name}:last_fail"

    async def _get_state(self) -> State:
        if self.redis is None:
            return State.CLOSED
        state = await self.redis.get(self._state_key)
        if not state:
            return State.CLOSED
        return State(state.decode() if isinstance(state, bytes) else state)

    async def _set_state(self, state: State):
        if self.redis is None:
            return
        old_state = await self._get_state()
        await self.redis.set(self._state_key, state.value)
        logger.info(f"Circuit Breaker '{self.name}' state changed to {state.value}")
        
        # Update metrics
        try:
            if state == State.OPEN and old_state != State.OPEN:
                circuit_breaker_trips.labels(provider=self.provider).inc()
                active_circuit_breakers_open.inc()
            elif old_state == State.OPEN and state != State.OPEN:
                active_circuit_breakers_open.dec()
        except Exception as e:
            logger.warning(f"Failed to update metrics: {e}")

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        if self.redis is None:
            return await func(*args, **kwargs)

        state = await self._get_state()
        
        if state == State.OPEN:
            last_fail = await self.redis.get(self._last_fail_time_key)
            if last_fail and time.time() - float(last_fail) > self.recovery_timeout:
                await self._set_state(State.HALF_OPEN)
                state = State.HALF_OPEN
            else:
                raise Exception(f"Circuit Breaker '{self.name}' is OPEN")

        try:
            result = await func(*args, **kwargs)
            if state == State.HALF_OPEN:
                await self._reset()
            return result
        except Exception as e:
            await self._handle_failure()
            raise e

    async def _handle_failure(self):
        if self.redis is None:
            return
        count = await self.redis.incr(self._fail_count_key)
        await self.redis.set(self._last_fail_time_key, time.time())
        
        if count >= self.threshold:
            await self._set_state(State.OPEN)

    async def _reset(self):
        if self.redis is None:
            return
        await self.redis.delete(self._fail_count_key)
        await self._set_state(State.CLOSED)
