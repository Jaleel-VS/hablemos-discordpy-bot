"""Async-aware LRU cache that deduplicates concurrent calls."""
import asyncio
import functools
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from typing import Any


def async_cache(maxsize: int = 128):
    """LRU cache for async functions. Concurrent calls with the same args share one task."""

    def decorator[**P, R](
        func: Callable[P, Coroutine[Any, Any, R]],
    ) -> Callable[P, Coroutine[Any, Any, R]]:
        cache: OrderedDict[tuple, asyncio.Task] = OrderedDict()

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = (args, tuple(sorted(kwargs.items())))

            if key in cache:
                task = cache[key]
                cache.move_to_end(key)
                if not task.done():
                    return await asyncio.shield(task)
                exc = task.exception()
                if exc is None:
                    return task.result()
                # Previous call failed — retry
                del cache[key]

            task = asyncio.create_task(func(*args, **kwargs))
            cache[key] = task
            if len(cache) > maxsize:
                cache.popitem(last=False)

            try:
                return await asyncio.shield(task)
            except BaseException:
                cache.pop(key, None)
                raise

        def invalidate(*args: Any, **kwargs: Any) -> None:
            key = (args, tuple(sorted(kwargs.items())))
            cache.pop(key, None)

        # Expose cache-management handles on the wrapped callable. These are
        # dynamic attributes, so set them via __dict__ to keep the declared
        # Callable return type intact.
        wrapper.__dict__["cache"] = cache
        wrapper.__dict__["invalidate"] = invalidate
        wrapper.__dict__["cache_clear"] = cache.clear
        return wrapper

    return decorator
