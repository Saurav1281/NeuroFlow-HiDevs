import asyncio
import logging
import time
from typing import Optional
from redis.asyncio import Redis

logger = logging.getLogger(__name__)

class RateLimiter:
    """Redis-backed async rate limiter for NeuroFlow."""
    
    def __init__(self, redis: Redis):
        self.redis = redis

    async def sliding_window_check(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int
    ) -> bool:
        """Sliding window rate limit check."""
        now = time.time()
        pipeline = self.redis.pipeline()
        
        # Add new request
        pipeline.zadd(key, {f"{now}_{window_seconds}": now})
        # Remove old requests
        pipeline.zremrangebyscore(key, 0, now - window_seconds)
        # Count remaining requests
        pipeline.zcard(key)
        # Set expiry for the key
        pipeline.expire(key, window_seconds + 1)
        
        _, _, count, _ = await pipeline.execute()
        
        return count <= limit

    async def token_bucket_check(
        self, 
        key: str, 
        limit: int, 
        window_seconds: int,
        refill_rate: float
    ) -> bool:
        """Token bucket rate limit check."""
        now = time.time()
        tokens = await self.redis.get(f"{key}:tokens")
        last_refill = await self.redis.get(f"{key}:last_refill")
        
        if tokens is None:
            tokens = float(limit)
            last_refill = now
        else:
            tokens = float(tokens)
            last_refill = float(last_refill)
            
            # Refill tokens
            elapsed = now - last_refill
            refill = elapsed * refill_rate
            tokens = min(float(limit), tokens + refill)
            last_refill = now
            
        if tokens >= 1.0:
            tokens -= 1.0
            await self.redis.set(f"{key}:tokens", tokens)
            await self.redis.set(f"{key}:last_refill", last_refill)
            return True
            
        return False
