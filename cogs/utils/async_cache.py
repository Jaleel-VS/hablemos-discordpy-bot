"""Async-aware LRU cache that deduplicates concurrent calls."""
import asyncio
import functools
from collections import OrderedDict


def async_cache(maxsize: int = 128):
    """LRU cache for async functions. Concurrent calls with the same args share one task."""

    def decorator[T](func: T) -> T:
        cache: OrderedDict[tuple, asyncio.Task] = OrderedDict()

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
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

        wrapper.cache = cache

        def invalidate(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            cache.pop(key, None)

        wrapper.invalidate = invalidate
        wrapper.cache_clear = cache.clear
        return wrapper

    return decorator
