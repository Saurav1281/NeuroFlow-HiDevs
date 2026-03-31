import asyncio
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class TimeoutManager:
    """Async timeout manager for wrapping sensitive operations."""

    @staticmethod
    async def run_with_timeout(
        func: Callable[..., Any], timeout: float, *args: Any, **kwargs: Any
    ) -> Any:  # noqa: ANN401
        try:
            return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        except TimeoutError:
            logger.error(f"Operation timed out after {timeout} seconds")
            raise Exception(f"Operation timed out after {timeout} seconds")
