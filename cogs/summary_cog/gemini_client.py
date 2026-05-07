"""Gemini client for generating conversation summaries."""
import logging

from cogs.utils.gemini_base import BaseGeminiClient

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """Summarize this Discord conversation for a moderator. Be concise and factual.

Rules:
- Use markdown bullet points
- Name participants when relevant
- Skip greetings, small talk, and bot commands unless they're the main topic
- If there are multiple threads/topics, separate them
- Max 400 words
- Do not editorialize or add opinions

{message_count} messages between {start_time} and {end_time}:

{messages}"""

FOCUSED_PROMPT = """You are a Discord moderation assistant. A moderator wants to find messages related to a specific topic in a conversation.

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

SUGGEST_TOPICS_PROMPT = """You are a Discord moderation assistant. A moderator wants help identifying topics worth investigating in this conversation.

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


class GeminiClient(BaseGeminiClient):
    """Generates conversation summaries via Gemini."""

    async def generate_summary(self, messages: list[dict], topic: str | None = None) -> str:
        """Generate a summary from a list of message dicts.

        Args:
            messages: List of message dicts with author, content, timestamp, and optionally link.
            topic: If provided, focus summary on this topic and include evidence links.
        """
        if not messages:
            return "No messages to summarize."

        formatted = []
        for msg in messages:
            content = msg['content'].strip()
            if not content:
                continue
            ts = msg['timestamp'].strftime('%H:%M')
            if topic and msg.get('link'):
                formatted.append(f"[{ts}] [MSG_LINK:{msg['link']}] {msg['author']}: {content}")
            else:
                formatted.append(f"[{ts}] {msg['author']}: {content}")

        if topic:
            prompt = FOCUSED_PROMPT.format(
                topic=topic,
                message_count=len(messages),
                start_time=messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M'),
                end_time=messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M'),
                messages='\n'.join(formatted),
            )
        else:
            prompt = SUMMARY_PROMPT.format(
                message_count=len(messages),
                start_time=messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M'),
                end_time=messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M'),
                messages='\n'.join(formatted),
            )

        text = await self._generate(prompt, temperature=0.2, max_output_tokens=1024)
        logger.info("Generated %ssummary for %s messages",
                    "focused " if topic else "", len(messages))
        return text or "Failed to generate summary."

    async def suggest_topics(self, messages: list[dict]) -> str:
        """Suggest focused topics a moderator could investigate."""
        if not messages:
            return "No messages to analyze."

        formatted = []
        for msg in messages:
            content = msg['content'].strip()
            if not content:
                continue
            ts = msg['timestamp'].strftime('%H:%M')
            formatted.append(f"[{ts}] {msg['author']}: {content}")

        prompt = SUGGEST_TOPICS_PROMPT.format(
            message_count=len(messages),
            start_time=messages[0]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            end_time=messages[-1]['timestamp'].strftime('%Y-%m-%d %H:%M'),
            messages='\n'.join(formatted),
        )

        text = await self._generate(prompt, temperature=0.3, max_output_tokens=1024)
        logger.info("Generated topic suggestions for %s messages", len(messages))
        return text or "Failed to generate topic suggestions."
