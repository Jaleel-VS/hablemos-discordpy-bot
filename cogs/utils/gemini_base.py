"""Shared async Gemini API client base."""
import asyncio
import logging
import random

from google import genai
from google.genai import types

from cogs.utils.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Single shared rate limiter across all Gemini clients (one API key)
_shared_rate_limiter = RateLimiter(requests_per_minute=15)


class BaseGeminiClient:
    """Base class for Gemini API clients with async support and retry logic."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash-lite"):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    async def _generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.7,
        max_output_tokens: int = 2048,
        top_p: float = 0.9,
        top_k: int = 40,
    ) -> str | None:
        """Generate content via the async Gemini API. Returns text or None."""
        await _shared_rate_limiter.wait_if_needed()
        response = await self.client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                max_output_tokens=max_output_tokens,
            ),
        )
        return response.text

    async def _generate_with_retry(
        self,
        prompt: str,
        *,
        max_retries: int = 3,
        **kwargs,
    ) -> str | None:
        """Call _generate with exponential backoff retries."""
        for attempt in range(max_retries):
            try:
                return await self._generate(prompt, **kwargs)
            except Exception:
                logger.exception("Gemini API error (attempt %s/%s)", attempt + 1, max_retries)
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait)
        return None
