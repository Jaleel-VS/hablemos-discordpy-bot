"""Prompts used by ``summary_cog``.

Three stateless prompt singletons:

- :data:`SUMMARY_PROMPT` — overview summary of a Discord message range.
- :data:`FOCUSED_SUMMARY_PROMPT` — topic-focused summary with evidence
  links per quoted message.
- :data:`SUGGEST_TOPICS_PROMPT` — proposes topics worth investigating
  in a message range.

Inputs are typed dataclasses where structure matters; the bare list
case (no extra parameters) takes :type:`MessageDicts` directly.
"""
from dataclasses import dataclass
from datetime import datetime

from cogs.utils.gemini import Prompt

SUMMARY_TEMPLATE = """Summarize this Discord conversation for a moderator. Be concise and factual.

Rules:
- Use markdown bullet points
- Name participants when relevant
- Skip greetings, small talk, and bot commands unless they're the main topic
- If there are multiple threads/topics, separate them
- Max 400 words
- Do not editorialize or add opinions

{message_count} messages between {start_time} and {end_time}:

{messages}"""

FOCUSED_TEMPLATE = """You are a Discord moderation assistant. A moderator wants to find messages related to a specific topic in a conversation.

**Topic to focus on:** {topic}

**Your task:**
1. Read through the messages carefully. Identify ONLY messages that are genuinely relevant to the topic above.
2. For each relevant message, output it in this exact format:
   - **[Author]** said: "quote" — [evidence]({{message_link}})
3. After listing the evidence, write a brief (2-3 sentence) summary of what happened regarding this topic.

Rules:
- ONLY include messages that are actually relevant to the specified topic. Do not stretch or infer relevance.
- Quote the actual message content exactly as written (trim if very long, but keep the key part). Do NOT fabricate or paraphrase quotes.
- Be factual, do not editorialize
- IMPORTANT: If no messages in the conversation are related to this topic, respond ONLY with: "No messages found related to this topic." Do not invent or hallucinate content that isn't there.
- Use the MSG_LINK provided next to each message for the evidence links. Do not make up links.

{message_count} messages between {start_time} and {end_time}:

{messages}"""

SUGGEST_TOPICS_TEMPLATE = """You are a Discord moderation assistant. A moderator wants help identifying topics worth investigating in this conversation.

**Your task:**
Read the messages below and suggest focused search prompts the moderator could use to dig into specific behaviors or topics present in this conversation.

**Output format:**
For each topic you identify, output:
- **Topic:** a short, specific prompt the moderator could use (e.g. "comments mocking user X's weight", "threats toward user Y")
- **Why:** one sentence explaining what you saw that suggests this is worth looking into
- **Participants:** who was involved

Rules:
- Only suggest topics that are ACTUALLY present in the messages. Do NOT invent or hallucinate topics.
- Focus on things a moderator would care about: harassment, bullying, slurs, threats, NSFW content, raids, spam, etc.
- If the conversation is benign and there's nothing concerning, respond ONLY with: "Nothing concerning found in this conversation."
- Be specific — "bullying" is too vague, "comments mocking ayeon's BMI/weight" is good.
- Max 5 topics, ordered by severity.

{message_count} messages between {start_time} and {end_time}:

{messages}"""


# A "message" dict carries: author, content, timestamp, and optionally
# link. Kept as dict for now to avoid invasive changes upstream.
type MessageDicts = list[dict]


@dataclass(frozen=True, slots=True)
class FocusedSummaryInput:
    """Input for :class:`FocusedSummaryPrompt`."""
    messages: MessageDicts
    topic: str


def _drop_empty(messages: MessageDicts) -> MessageDicts:
    return [m for m in messages if m["content"].strip()]


def _require_non_empty(messages: MessageDicts) -> None:
    """Render contract: cogs pre-filter empty / bot messages before calling.

    Raises :class:`ValueError` if violated — a bug, not a user-visible
    failure.
    """
    if not messages:
        raise ValueError(
            "messages list cannot be empty after dropping empties; "
            "the cog should pre-filter before calling render()",
        )


def _time_window(messages: MessageDicts) -> tuple[str, str]:
    fmt = "%Y-%m-%d %H:%M"
    start: datetime = messages[0]["timestamp"]
    end: datetime = messages[-1]["timestamp"]
    return start.strftime(fmt), end.strftime(fmt)


def _format_plain(messages: MessageDicts) -> list[str]:
    return [
        f"[{m['timestamp'].strftime('%H:%M')}] {m['author']}: {m['content'].strip()}"
        for m in messages
    ]


def _format_with_links(messages: MessageDicts) -> list[str]:
    out: list[str] = []
    for m in messages:
        ts = m["timestamp"].strftime("%H:%M")
        link = m.get("link")
        if link:
            out.append(f"[{ts}] [MSG_LINK:{link}] {m['author']}: {m['content'].strip()}")
        else:
            out.append(f"[{ts}] {m['author']}: {m['content'].strip()}")
    return out


class SummaryPrompt(Prompt[MessageDicts, str]):
    """Overview summary of a Discord message range."""

    feature = "summary"
    temperature = 0.2
    max_output_tokens = 1024

    def render(self, inp: MessageDicts) -> str:
        msgs = _drop_empty(inp)
        _require_non_empty(msgs)
        start, end = _time_window(msgs)
        return SUMMARY_TEMPLATE.format(
            message_count=len(msgs),
            start_time=start,
            end_time=end,
            messages="\n".join(_format_plain(msgs)),
        )

    def parse(self, text: str) -> str:
        return text or "Failed to generate summary."


class FocusedSummaryPrompt(Prompt[FocusedSummaryInput, str]):
    """Topic-focused summary with per-message evidence links."""

    feature = "summary"
    temperature = 0.2
    max_output_tokens = 1024

    def render(self, inp: FocusedSummaryInput) -> str:
        msgs = _drop_empty(inp.messages)
        _require_non_empty(msgs)
        start, end = _time_window(msgs)
        return FOCUSED_TEMPLATE.format(
            topic=inp.topic,
            message_count=len(msgs),
            start_time=start,
            end_time=end,
            messages="\n".join(_format_with_links(msgs)),
        )

    def parse(self, text: str) -> str:
        return text or "Failed to generate summary."


class SuggestTopicsPrompt(Prompt[MessageDicts, str]):
    """Suggests focused topics a moderator could investigate."""

    feature = "summary"
    temperature = 0.3
    max_output_tokens = 1024

    def render(self, inp: MessageDicts) -> str:
        msgs = _drop_empty(inp)
        _require_non_empty(msgs)
        start, end = _time_window(msgs)
        return SUGGEST_TOPICS_TEMPLATE.format(
            message_count=len(msgs),
            start_time=start,
            end_time=end,
            messages="\n".join(_format_plain(msgs)),
        )

    def parse(self, text: str) -> str:
        return text or "Failed to generate topic suggestions."


SUMMARY_PROMPT = SummaryPrompt()
FOCUSED_SUMMARY_PROMPT = FocusedSummaryPrompt()
SUGGEST_TOPICS_PROMPT = SuggestTopicsPrompt()


__all__ = [
    "FOCUSED_SUMMARY_PROMPT",
    "SUGGEST_TOPICS_PROMPT",
    "SUMMARY_PROMPT",
    "FocusedSummaryInput",
    "FocusedSummaryPrompt",
    "SuggestTopicsPrompt",
    "SummaryPrompt",
]
