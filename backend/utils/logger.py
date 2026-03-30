import logging
import asyncio
import functools
import time
from typing import Callable, Any, Type, Union, Tuple
from fastapi import HTTPException

import os

# Configure centralized logger
handlers = [logging.StreamHandler()]
# Only add FileHandler if we are not in a read-only environment or if explicitly requested
if os.access('.', os.W_OK):
    try:
        handlers.append(logging.FileHandler('system.log'))
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)
logger = logging.getLogger("neuroflow")

def retry_on_failure(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception
):
    """
    Decorator for retrying asynchronous functions with exponential backoff.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == retries - 1:
                        logger.error(f"Function {func.__name__} failed after {retries} attempts: {e}")
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}, retrying in {current_delay}s... Error: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
        return wrapper
    return decorator

def handle_errors(func: Callable):
    """
    Decorator for centralized error handling in API endpoints.
    Catches exceptions and raises appropriate FastAPI HTTPExceptions.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except ValueError as e:
            logger.error(f"Value error in {func.__name__}: {e}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="An internal server error occurred.")
    return wrapper
