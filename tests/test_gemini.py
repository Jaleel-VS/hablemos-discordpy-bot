"""Unit tests for the Gemini deep module.

Tests drive ``Gemini`` directly without a real ``genai.Client`` by
overriding ``_generate_content`` in a test subclass.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from google.genai import errors as genai_errors

from cogs.ask_cog.prompts import ASK_PROMPT, AskPrompt
from cogs.conversation_cog.prompts import (
    CONVERSATION_PROMPT,
    ConversationInput,
    ParsedConversation,
)
from cogs.practice_cog.prompts import PRACTICE_SENTENCE_PROMPT, PracticeWord
from cogs.summary_cog.prompts import (
    FOCUSED_SUMMARY_PROMPT,
    SUGGEST_TOPICS_PROMPT,
    SUMMARY_PROMPT,
    FocusedSummaryInput,
)
from cogs.utils.gemini import Gemini, GeminiError, Prompt
from cogs.utils.rate_limiter import RateLimiter


def _client_error(code: int, message: str = "boom", status: str = "ERROR") -> genai_errors.ClientError:
    return genai_errors.ClientError(
        code, {"error": {"code": code, "message": message, "status": status}},
    )


def _server_error(code: int = 500, message: str = "server boom") -> genai_errors.ServerError:
    return genai_errors.ServerError(
        code, {"error": {"code": code, "message": message, "status": "INTERNAL"}},
    )


class _TestGemini(Gemini):
    """``Gemini`` subclass with a scriptable ``_generate_content``.

    Bypasses ``genai.Client`` construction so tests don't need an API
    key and never make network calls. ``actions`` is consumed in order
    on each call: a string is returned as the response text, an
    Exception is raised.
    """

    def __init__(self, *, default_model: str = "gemini-test", actions=None):
        # Skip Gemini.__init__ — we never use self._client because
        # _generate_content is overridden below.
        self._default_model = default_model
        self._rate_limiter = RateLimiter(requests_per_minute=600)  # effectively no-op
        self._actions: list = list(actions or [])
        self.calls: list[dict] = []

    async def _generate_content(self, *, model, prompt, config):  # type: ignore[override]
        self.calls.append({"model": model, "prompt": prompt, "config": config})
        if not self._actions:
            return ""
        action = self._actions.pop(0)
        if isinstance(action, BaseException):
            raise action
        return action


# ---------- Prompt validation ----------


class _NoFeaturePrompt(Prompt[str, str]):
    # Intentionally no `feature` set.
    def render(self, inp: str) -> str:
        return inp

    def parse(self, text: str, inp: str) -> str:
        return text


@pytest.mark.asyncio
async def test_resolve_model_rejects_prompt_without_feature():
    g = _TestGemini()
    with pytest.raises(ValueError, match="feature is empty"):
        await g.run(_NoFeaturePrompt(), "hi")


# ---------- Model resolution ----------


@pytest.mark.asyncio
async def test_per_feature_env_var_overrides_default(monkeypatch):
    monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_ASK_MODEL", "gemini-from-env")
    g = _TestGemini(default_model="gemini-builtin", actions=["ok"])

    await g.run(ASK_PROMPT, "hello")

    assert g.calls[0]["model"] == "gemini-from-env"


@pytest.mark.asyncio
async def test_default_model_used_when_per_feature_unset(monkeypatch):
    monkeypatch.delenv("GEMINI_ASK_MODEL", raising=False)
    g = _TestGemini(default_model="gemini-default", actions=["ok"])

    await g.run(ASK_PROMPT, "hello")

    assert g.calls[0]["model"] == "gemini-default"


def test_default_model_falls_back_to_env_then_constant(monkeypatch):
    monkeypatch.setenv("GEMINI_DEFAULT_MODEL", "gemini-from-env-default")
    g = _TestGemini.__new__(_TestGemini)
    Gemini.__init__(g, "fake-key")
    assert g._default_model == "gemini-from-env-default"

    monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
    g2 = _TestGemini.__new__(_TestGemini)
    Gemini.__init__(g2, "fake-key")
    # built-in fallback is documented as gemini-3.5-flash
    assert g2._default_model == "gemini-3.5-flash"


# ---------- Error mapping (no retry on client errors) ----------


@pytest.mark.asyncio
async def test_404_raises_with_model_config_user_message():
    g = _TestGemini(actions=[_client_error(404, "model not found")])

    with pytest.raises(GeminiError) as exc_info:
        await g.run(ASK_PROMPT, "hi")

    err = exc_info.value
    assert err.code == 404
    assert "model is unavailable" in err.user_message.lower()
    assert "gemini_" in err.user_message.lower()  # mentions the env var
    assert len(g.calls) == 1  # never retried


@pytest.mark.asyncio
async def test_429_raises_with_rate_limit_message():
    g = _TestGemini(actions=[_client_error(429, "too many requests")])

    with pytest.raises(GeminiError) as exc_info:
        await g.run(ASK_PROMPT, "hi")

    assert exc_info.value.code == 429
    assert "rate limited" in exc_info.value.user_message.lower()
    assert len(g.calls) == 1


@pytest.mark.asyncio
async def test_401_raises_with_auth_message():
    g = _TestGemini(actions=[_client_error(401, "unauthorized")])

    with pytest.raises(GeminiError) as exc_info:
        await g.run(ASK_PROMPT, "hi")

    assert exc_info.value.code == 401
    assert "auth" in exc_info.value.user_message.lower()
    assert len(g.calls) == 1


# ---------- Retry behavior ----------


@pytest.mark.asyncio
async def test_server_error_retries_then_returns(monkeypatch):
    # No-op sleep so the retry test runs instantly.
    import cogs.utils.gemini as gemini_mod
    sleeps: list[float] = []
    async def fake_sleep(seconds):
        sleeps.append(seconds)
    monkeypatch.setattr(gemini_mod.asyncio, "sleep", fake_sleep)

    g = _TestGemini(actions=[_server_error(503), _server_error(503), "recovered"])

    result = await g.run(ASK_PROMPT, "hi")

    assert result == "recovered"
    assert len(g.calls) == 3
    assert len(sleeps) == 2  # two backoff sleeps between three attempts


@pytest.mark.asyncio
async def test_server_error_exhausts_retries_then_raises(monkeypatch):
    import cogs.utils.gemini as gemini_mod
    async def fake_sleep(_):
        return None
    monkeypatch.setattr(gemini_mod.asyncio, "sleep", fake_sleep)

    g = _TestGemini(actions=[_server_error(500)] * 5)

    with pytest.raises(GeminiError) as exc_info:
        await g.run(ASK_PROMPT, "hi")

    assert exc_info.value.code == 500
    assert "trouble" in exc_info.value.user_message.lower()
    assert len(g.calls) == 3  # MAX_RETRIES


# ---------- Happy path ----------


@pytest.mark.asyncio
async def test_run_round_trip_renders_and_parses():
    class _DoublePrompt(Prompt[str, str]):
        feature = "double"
        def render(self, inp: str) -> str:
            return f"prompt({inp})"
        def parse(self, text: str, inp: str) -> str:
            return f"{text}|{inp}"  # demonstrates inp is available in parse

    g = _TestGemini(actions=["xyz"])
    result = await g.run(_DoublePrompt(), "in")

    assert result == "xyz|in"
    assert g.calls[0]["prompt"] == "prompt(in)"


# ---------- Ask prompt smoke ----------


def test_ask_prompt_passthrough():
    assert ASK_PROMPT.feature == "ask"
    assert ASK_PROMPT.render("hello world") == "hello world"
    assert ASK_PROMPT.parse("response text", "hello world") == "response text"
    assert isinstance(ASK_PROMPT, AskPrompt)


# ---------- Summary prompts ----------


def _msg(author: str, content: str, hour: int = 12, minute: int = 0, link: str | None = None) -> dict:
    m = {
        "author": author,
        "content": content,
        "timestamp": datetime(2026, 1, 1, hour, minute),
    }
    if link is not None:
        m["link"] = link
    return m


def test_summary_prompt_render_includes_count_and_window():
    rendered = SUMMARY_PROMPT.render([
        _msg("alice", "hello", hour=10),
        _msg("bob", "world", hour=11),
    ])
    assert "2 messages between" in rendered
    assert "2026-01-01 10:00" in rendered
    assert "2026-01-01 11:00" in rendered
    assert "alice: hello" in rendered
    assert "bob: world" in rendered


def test_summary_prompt_drops_empty_content():
    rendered = SUMMARY_PROMPT.render([
        _msg("alice", "   ", hour=10),  # only whitespace, dropped
        _msg("bob", "hello", hour=11),
    ])
    assert "1 messages between" in rendered
    assert "alice" not in rendered


def test_summary_prompt_rejects_empty_after_dropping():
    with pytest.raises(ValueError, match="empty"):
        SUMMARY_PROMPT.render([_msg("alice", "   ")])


def test_summary_prompt_parse_returns_placeholder_on_empty():
    msgs = [_msg("alice", "hi")]
    assert SUMMARY_PROMPT.parse("", msgs) == "Failed to generate summary."
    assert SUMMARY_PROMPT.parse("actual response", msgs) == "actual response"


def test_focused_summary_prompt_includes_topic_and_msg_links():
    inp = FocusedSummaryInput(
        messages=[
            _msg("alice", "discusses topic", link="https://discord.com/channels/1/2/3"),
            _msg("bob", "replies", link="https://discord.com/channels/1/2/4"),
        ],
        topic="alice's behavior",
    )
    rendered = FOCUSED_SUMMARY_PROMPT.render(inp)
    assert "alice's behavior" in rendered
    assert "[MSG_LINK:https://discord.com/channels/1/2/3]" in rendered
    assert "[MSG_LINK:https://discord.com/channels/1/2/4]" in rendered


def test_focused_summary_prompt_handles_messages_without_link():
    inp = FocusedSummaryInput(
        messages=[_msg("alice", "hello")],  # no link key
        topic="general",
    )
    rendered = FOCUSED_SUMMARY_PROMPT.render(inp)
    # Template prose mentions "MSG_LINK"; only the bracketed form
    # "[MSG_LINK:...]" appears when a message actually carries a link.
    assert "[MSG_LINK:" not in rendered
    assert "alice: hello" in rendered


def test_suggest_topics_prompt_renders_plain():
    rendered = SUGGEST_TOPICS_PROMPT.render([
        _msg("alice", "hello", hour=9),
        _msg("bob", "hi", hour=10),
    ])
    assert "hello" in rendered
    assert "hi" in rendered
    assert "[MSG_LINK:" not in rendered  # plain format only


def test_summary_prompts_share_feature_slug():
    # All three resolve GEMINI_SUMMARY_MODEL via the same feature key.
    assert SUMMARY_PROMPT.feature == "summary"
    assert FOCUSED_SUMMARY_PROMPT.feature == "summary"
    assert SUGGEST_TOPICS_PROMPT.feature == "summary"


# ---------- Practice prompt ----------


def test_practice_sentence_prompt_renders_with_language_name():
    rendered = PRACTICE_SENTENCE_PROMPT.render(
        PracticeWord(word="hablar", translation="to speak", language="spanish"),
    )
    assert "Spanish" in rendered
    assert '"hablar"' in rendered
    assert "to speak" in rendered

    rendered_en = PRACTICE_SENTENCE_PROMPT.render(
        PracticeWord(word="speak", translation="hablar", language="english"),
    )
    assert "English" in rendered_en


def test_practice_parse_returns_sentence_and_cloze():
    inp = PracticeWord(word="hablar", translation="to speak", language="spanish")
    text = "Mi hermana puede hablar tres idiomas diferentes."
    result = PRACTICE_SENTENCE_PROMPT.parse(text, inp)

    assert result is not None
    sentence, cloze = result
    assert sentence == text
    assert cloze == "Mi hermana puede ___ tres idiomas diferentes."


def test_practice_parse_strips_whitespace():
    inp = PracticeWord(word="book", translation="libro", language="english")
    result = PRACTICE_SENTENCE_PROMPT.parse(
        "\n  I read a book yesterday.  \n", inp,
    )
    assert result == ("I read a book yesterday.", "I read a ___ yesterday.")


def test_practice_parse_word_boundary_match_only():
    # "book" should match the standalone word, not "booking" or "cookbook".
    inp = PracticeWord(word="book", translation="libro", language="english")
    result = PRACTICE_SENTENCE_PROMPT.parse(
        "My cookbook has a booking for tonight.", inp,
    )
    # No standalone "book" — reject.
    assert result is None


def test_practice_parse_case_insensitive_match():
    inp = PracticeWord(word="hablar", translation="to speak", language="spanish")
    text = "Hablar bien requiere mucha pr\u00e1ctica."
    result = PRACTICE_SENTENCE_PROMPT.parse(text, inp)

    assert result is not None
    sentence, cloze = result
    assert sentence == text
    # The matched form ("Hablar") was replaced with the blank.
    assert cloze == "___ bien requiere mucha pr\u00e1ctica."


def test_practice_parse_returns_none_when_word_missing():
    inp = PracticeWord(word="hablar", translation="to speak", language="spanish")
    result = PRACTICE_SENTENCE_PROMPT.parse(
        "Esta oraci\u00f3n no tiene la palabra clave.", inp,
    )
    assert result is None


def test_practice_parse_returns_none_on_empty_text():
    inp = PracticeWord(word="hablar", translation="to speak", language="spanish")
    assert PRACTICE_SENTENCE_PROMPT.parse("", inp) is None
    assert PRACTICE_SENTENCE_PROMPT.parse("   ", inp) is None


def test_practice_prompt_feature_slug():
    assert PRACTICE_SENTENCE_PROMPT.feature == "practice"


# ---------- Conversation prompt ----------


_CONVO_INP = ConversationInput(
    language="spanish",
    level="beginner",
    category="restaurant",
    scenario="You are ordering food at a family restaurant",
)


_HAPPY_RESPONSE = """SCENARIO: Est\u00e1s ordenando comida en un restaurante familiar
SPEAKER1: Ana (mesera)
SPEAKER2: Miguel (cliente)
CONVERSATION:
Ana: Buenas tardes. \u00bfEst\u00e1 listo para ordenar?
Miguel: S\u00ed, por favor. \u00bfQu\u00e9 me recomienda?
Ana: El pollo asado es muy popular hoy.
Miguel: Perfecto, tomar\u00e9 eso.
Ana: \u00bfY para tomar?
Miguel: Una limonada, gracias.
Ana: Enseguida se lo traigo.
Miguel: Muchas gracias."""


def test_conversation_prompt_render_includes_language_level_category_and_scenario():
    rendered = CONVERSATION_PROMPT.render(_CONVO_INP)
    assert "Spanish" in rendered
    assert "Beginner" in rendered
    assert "Restaurant" in rendered
    assert _CONVO_INP.scenario in rendered


def test_conversation_prompt_temperature_varies_by_level():
    # 0.7 / 0.8 / 0.9 from conversation_data.LEVELS
    assert CONVERSATION_PROMPT.resolve_temperature(_CONVO_INP) == 0.7
    intermediate = ConversationInput(
        language="spanish", level="intermediate",
        category="restaurant", scenario="x",
    )
    advanced = ConversationInput(
        language="spanish", level="advanced",
        category="restaurant", scenario="x",
    )
    assert CONVERSATION_PROMPT.resolve_temperature(intermediate) == 0.8
    assert CONVERSATION_PROMPT.resolve_temperature(advanced) == 0.9


def test_conversation_parse_happy_path():
    result = CONVERSATION_PROMPT.parse(_HAPPY_RESPONSE, _CONVO_INP)
    assert isinstance(result, ParsedConversation)
    assert result.scenario == "Est\u00e1s ordenando comida en un restaurante familiar"
    assert result.speaker1 == "Ana (mesera)"
    assert result.speaker2 == "Miguel (cliente)"
    # All eight CONVERSATION lines preserved, joined with newlines.
    assert result.conversation.count("\n") == 7
    assert result.conversation.startswith("Ana: Buenas tardes")
    assert result.conversation.endswith("Miguel: Muchas gracias.")


def test_conversation_parse_returns_none_when_scenario_missing():
    bad = _HAPPY_RESPONSE.replace(
        "SCENARIO: Est\u00e1s ordenando comida en un restaurante familiar\n",
        "",
    )
    assert CONVERSATION_PROMPT.parse(bad, _CONVO_INP) is None


def test_conversation_parse_returns_none_when_speaker1_missing():
    bad = _HAPPY_RESPONSE.replace("SPEAKER1: Ana (mesera)\n", "")
    assert CONVERSATION_PROMPT.parse(bad, _CONVO_INP) is None


def test_conversation_parse_returns_none_when_speaker2_missing():
    bad = _HAPPY_RESPONSE.replace("SPEAKER2: Miguel (cliente)\n", "")
    assert CONVERSATION_PROMPT.parse(bad, _CONVO_INP) is None


def test_conversation_parse_returns_none_when_no_conversation_lines():
    text = "SCENARIO: x\nSPEAKER1: a\nSPEAKER2: b\nCONVERSATION:\n"
    assert CONVERSATION_PROMPT.parse(text, _CONVO_INP) is None


def test_conversation_parse_accepts_short_conversation_with_warning(caplog):
    # Less than 6 lines logs a warning but still returns a result.
    text = (
        "SCENARIO: x\n"
        "SPEAKER1: a\n"
        "SPEAKER2: b\n"
        "CONVERSATION:\n"
        "a: hi\n"
        "b: hello\n"
    )
    with caplog.at_level("WARNING"):
        result = CONVERSATION_PROMPT.parse(text, _CONVO_INP)
    assert isinstance(result, ParsedConversation)
    assert "Short conversation" in caplog.text


def test_conversation_parse_returns_none_on_empty_text():
    assert CONVERSATION_PROMPT.parse("", _CONVO_INP) is None


def test_conversation_parse_returns_none_on_unstructured_text():
    # No SCENARIO/SPEAKER prefixes anywhere.
    text = "This is just a plain paragraph. No structure at all."
    assert CONVERSATION_PROMPT.parse(text, _CONVO_INP) is None


def test_conversation_parse_strips_whitespace_around_fields():
    text = (
        "SCENARIO:    leading and trailing whitespace   \n"
        "   SPEAKER1:    Ana    \n"
        "SPEAKER2:Bob\n"
        "CONVERSATION:\n"
        "Ana: hi\n"
        "Bob: hello\n"
        "Ana: bye\n"
        "Bob: bye\n"
        "Ana: cheers\n"
        "Bob: cheers\n"
    )
    result = CONVERSATION_PROMPT.parse(text, _CONVO_INP)
    assert isinstance(result, ParsedConversation)
    assert result.scenario == "leading and trailing whitespace"
    assert result.speaker1 == "Ana"
    assert result.speaker2 == "Bob"


def test_conversation_prompt_feature_slug():
    assert CONVERSATION_PROMPT.feature == "conversation"
