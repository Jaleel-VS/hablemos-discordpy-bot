"""Prompts used by ``ask_cog``.

Each prompt is a stateless singleton — instantiate once at import time
and pass the same instance to ``bot.gemini.run`` on every call.
"""
from cogs.utils.gemini import Prompt


class AskPrompt(Prompt[str, str]):
    """Owner-only free-form Q&A.

    Input: the user's question, used verbatim.
    Output: Gemini's text response, untouched (the cog paginates it).
    """

    feature = "ask"
    temperature = 0.7
    max_output_tokens = 4096

    def render(self, question: str) -> str:
        return question

    def parse(self, text: str, inp: str) -> str:
        return text


ASK_PROMPT = AskPrompt()
