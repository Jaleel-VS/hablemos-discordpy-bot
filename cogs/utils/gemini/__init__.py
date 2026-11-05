"""Typed Gemini execution with shared model selection, deadlines, and retries.

Prompts own rendering, parsing, and optional ``timeout_seconds`` overrides.
``run`` bounds rate-limit waits and retries as well as the network call, mapping
expired deadlines to ``GeminiError`` for every caller. Models can be selected
with ``GEMINI_<FEATURE>_MODEL`` or ``GEMINI_DEFAULT_MODEL``.
"""
import asyncio
import logging
import random

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from cogs.utils.rate_limiter import RateLimiter
from config import get_str_env

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
        response_mime_type: Set to ``"application/json"`` to enable
            structured output. Requires ``response_schema`` to be set.
        response_schema: A Pydantic ``BaseModel`` class or JSON schema
            dict. Gemini constrains its output to match this schema.
    """

    feature: str = ""
    temperature: float = 0.7
    max_output_tokens: int = 2048
    top_p: float = 0.9
    top_k: int = 40
    response_mime_type: str | None = None
    response_schema: type | None = None
    timeout_seconds: float = 30

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

    def resolve_temperature(self, inp: I) -> float:
        """Per-input temperature override hook.

        Defaults to the class-level :attr:`temperature` constant. Override
        when generation temperature should vary with the input (e.g.
        difficulty level), keeping the variation table next to the
        prompt rather than at the call site.
        """
        return self.temperature


class Gemini:
    """Single deep module for all Gemini calls."""

    def __init__(self, api_key: str, *, default_model: str | None = None):
        if not api_key:
            raise ValueError("api_key is required to construct Gemini")
        self._client = genai.Client(api_key=api_key)
        self._default_model = (
            default_model
            or get_str_env("GEMINI_DEFAULT_MODEL", DEFAULT_MODEL_FALLBACK)
        )
        self._rate_limiter = RateLimiter(requests_per_minute=RATE_LIMIT_RPM)

    def _resolve_model(self, prompt: Prompt) -> str:
        """``GEMINI_<FEATURE>_MODEL`` → instance default → fallback."""
        if not prompt.feature:
            raise ValueError(
                f"{type(prompt).__name__}.feature is empty; subclasses must set it",
            )
        env_var = f"GEMINI_{prompt.feature.upper()}_MODEL"
        return get_str_env(env_var, self._default_model)

    async def run[I, O](self, prompt: Prompt[I, O], inp: I) -> O:
        """Run ``prompt`` against Gemini.

        Returns the parsed output. Raises :class:`GeminiError` on
        failure (with a ``.user_message`` suitable for the user). Server
        errors retry with exponential backoff; client errors do not.
        """
        rendered = prompt.render(inp)
        model = self._resolve_model(prompt)
        config_kwargs: dict = {
            "temperature": prompt.resolve_temperature(inp),
            "top_p": prompt.top_p,
            "top_k": prompt.top_k,
            "max_output_tokens": prompt.max_output_tokens,
        }
        if prompt.response_mime_type:
            config_kwargs["response_mime_type"] = prompt.response_mime_type
        if prompt.response_schema:
            config_kwargs["response_schema"] = prompt.response_schema
        config = types.GenerateContentConfig(**config_kwargs)
        try:
            async with asyncio.timeout(prompt.timeout_seconds):
                text = await self._call_with_retry(
                    feature=prompt.feature, model=model, prompt=rendered, config=config,
                )
        except TimeoutError as exc:
            raise GeminiError(
                code=408,
                message="Gemini call deadline expired",
                user_message=f"Gemini didn't respond within {prompt.timeout_seconds:g}s. Try again.",
            ) from exc
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

        assert last_server_err is not None
        raise GeminiError(
            code=last_server_err.code,
            message=getattr(last_server_err, "message", None) or str(last_server_err),
            user_message=user_message_for(last_server_err),
        ) from last_server_err
