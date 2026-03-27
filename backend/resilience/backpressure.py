import asyncio
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

class BackpressureManager:
    """Async backpressure manager for monitoring queue depth."""
    
    def __init__(self, max_buffer_size: int = 100):
        self.max_buffer_size = max_buffer_size
        self._current_buffer = 0
        self._lock = asyncio.Lock()

    async def acquire_slot(self):
        """Acquire a slot in the buffer, or wait if full."""
        while self._current_buffer >= self.max_buffer_size:
            logger.warning("Backpressure: Buffer full, waiting for slot...")
            await asyncio.sleep(0.1)
        
        async with self._lock:
            self._current_buffer += 1

    async def release_slot(self):
        """Release a slot in the buffer."""
        async with self._lock:
            self._current_buffer = max(0, self._current_buffer - 1)

class TimeoutManager:
    """Async timeout manager for wrapping sensitive operations."""
    
    @staticmethod
    async def run_with_timeout(
        func: Callable, 
        timeout: float, 
        *args, 
        **kwargs
    ) -> Any:
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Operation timed out after {timeout} seconds")
            raise Exception(f"Operation timed out after {timeout} seconds")
