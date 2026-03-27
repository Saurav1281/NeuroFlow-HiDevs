import asyncio
import logging
from typing import Callable, Any, Optional

logger = logging.getLogger(__name__)

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
