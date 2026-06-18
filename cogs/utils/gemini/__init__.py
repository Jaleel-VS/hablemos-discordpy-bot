"""Gemini deep module — prompt registry + dispatcher.

One module owns the ``genai.Client`` instance, model resolution
(``GEMINI_<FEATURE>_MODEL`` → ``GEMINI_DEFAULT_MODEL`` → built-in
default), the shared rate limiter, retry-on-5xx, and HTTP-code-aware
error mapping (``GeminiError.user_message``). Cogs interact only via
:meth:`Gemini.run`.

Public API:
    :class:`Prompt` — base class for typed prompts (``render`` + ``parse``).
    :class:`Gemini` — runtime; constructed once and attached to ``bot.gemini``.
    :class:`GeminiError` — raised on any failure.

Adding a new Gemini-using feature:

    1. Subclass ``Prompt[I, O]`` in your cog's ``prompts.py``. Set
       ``feature`` to a short slug; declare ``temperature`` /
       ``max_output_tokens`` / etc. Implement ``render`` and ``parse``.
    2. Declare a module-level singleton: ``MY_PROMPT = MyPrompt()``.
    3. In your cog: ``result = await self.bot.gemini.run(MY_PROMPT, inp)``
       inside ``try / except GeminiError as e: await ctx.send(e.user_message)``.

The model can be overridden at deploy time without touching code by
setting ``GEMINI_<FEATURE>_MODEL`` (e.g. ``GEMINI_ASK_MODEL``).
"""
import asyncio
import logging
import os
import random

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from cogs.utils.rate_limiter import RateLimiter

from .errors import GeminiError, user_message_for

__all__ = ["Gemini", "GeminiError", "Prompt"]

logger = logging.getLogger(__name__)

DEFAULT_MODEL_FALLBACK = "gemini-3.5-flash"
RATE_LIMIT_RPM = 15
MAX_RETRIES = 3


class Prompt[I, O]:
    """Typed Gemini prompt: input ``I`` → output ``O``.

    Subclasses set the feature slug and generation config as class-level
    attributes, then implement :meth:`render` and :meth:`parse`. Prompts
    are stateless — declare one module-level singleton per prompt.

    Attributes:
        feature: Short slug (e.g. ``"ask"``, ``"summary"``). Picks the
            ``GEMINI_<FEATURE>_MODEL`` env var override.
        temperature, top_p, top_k, max_output_tokens: Generation config
            forwarded to ``GenerateContentConfig``.
    """

    feature: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 2048
    top_p: float = 0.9
    top_k: int = 40

    def render(self, inp: I) -> str:
        """Render the prompt template with ``inp``. Override in subclass."""
        raise NotImplementedError

    def parse(self, text: str, inp: I) -> O:
        """Parse the Gemini response into ``O``.

        Receives both the response text and the original input so
        post-processing that needs the prompt's input (e.g. the
        original word for a cloze-blank substitution) stays inside
        the prompt module rather than leaking into the cog.
        Override in subclass.
        """
        raise NotImplementedError


class Gemini:
    """Single deep module for all Gemini calls."""

    def __init__(self, api_key: str, *, default_model: str | None = None):
        if not api_key:
            raise ValueError("api_key is required to construct Gemini")
        self._client = genai.Client(api_key=api_key)
        self._default_model = (
            default_model
            or os.getenv("GEMINI_DEFAULT_MODEL")
            or DEFAULT_MODEL_FALLBACK
        )
        self._rate_limiter = RateLimiter(requests_per_minute=RATE_LIMIT_RPM)

    def _resolve_model(self, prompt: Prompt) -> str:
        """``GEMINI_<FEATURE>_MODEL`` → instance default → fallback."""
        if not prompt.feature:
            raise ValueError(
                f"{type(prompt).__name__}.feature is empty; subclasses must set it",
            )
        env_var = f"GEMINI_{prompt.feature.upper()}_MODEL"
        return os.getenv(env_var) or self._default_model

    async def run[I, O](self, prompt: Prompt[I, O], inp: I) -> O:
        """Run ``prompt`` against Gemini.

        Returns the parsed output. Raises :class:`GeminiError` on
        failure (with a ``.user_message`` suitable for the user). Server
        errors retry with exponential backoff; client errors do not.
        """
        rendered = prompt.render(inp)
        model = self._resolve_model(prompt)
        config = types.GenerateContentConfig(
            temperature=prompt.temperature,
            top_p=prompt.top_p,
            top_k=prompt.top_k,
            max_output_tokens=prompt.max_output_tokens,
        )
        text = await self._call_with_retry(
            feature=prompt.feature, model=model, prompt=rendered, config=config,
        )
        return prompt.parse(text, inp)

    async def _generate_content(
        self,
        *,
        model: str,
        prompt: str,
        config: types.GenerateContentConfig,
    ) -> str:
        """Single Gemini API call. Override in tests."""
        response = await self._client.aio.models.generate_content(
            model=model, contents=prompt, config=config,
        )
        return response.text or ""

    async def _call_with_retry(
        self,
        *,
        feature: str,
        model: str,
        prompt: str,
        config: types.GenerateContentConfig,
    ) -> str:
        """Retry only on ``ServerError``; client errors surface immediately."""
        last_server_err: genai_errors.ServerError | None = None
        for attempt in range(MAX_RETRIES):
            await self._rate_limiter.wait_if_needed()
            try:
                return await self._generate_content(
                    model=model, prompt=prompt, config=config,
                )
            except genai_errors.ClientError as e:
                logger.error(
                    "Gemini client error feature=%s code=%s: %s",
                    feature, e.code, e, exc_info=True,
                )
                raise GeminiError(
                    code=e.code,
                    message=getattr(e, "message", None) or str(e),
                    user_message=user_message_for(e),
                ) from e
            except genai_errors.ServerError as e:
                last_server_err = e
                logger.warning(
                    "Gemini server error feature=%s attempt=%s/%s code=%s: %s",
                    feature, attempt + 1, MAX_RETRIES, e.code, e,
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep((2 ** attempt) + random.uniform(0, 1))
                continue
            except genai_errors.APIError as e:
                logger.error(
                    "Gemini API error feature=%s code=%s: %s",
                    feature, getattr(e, "code", "?"), e, exc_info=True,
                )
                raise GeminiError(
                    code=getattr(e, "code", 0) or 0,
                    message=getattr(e, "message", None) or str(e),
                    user_message=user_message_for(e),
                ) from e

        # All MAX_RETRIES attempts hit ServerError — surface it.
        assert last_server_err is not None
        raise GeminiError(
            code=last_server_err.code,
            message=getattr(last_server_err, "message", None) or str(last_server_err),
            user_message=user_message_for(last_server_err),
        ) from last_server_err
