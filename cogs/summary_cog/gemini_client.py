"""
Google Gemini API client for generating conversation summaries
"""
import os
import logging
from typing import List, Dict
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


class GeminiClient:
    """Wrapper for Google Gemini API for conversation summarization"""

    def __init__(self):
        """
        Initialize Gemini client

        Raises:
            ValueError: If GEMINI_API_KEY environment variable is not set
        """
        # Get API key from environment
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is required")

        # Initialize the client with API key
        self.client = genai.Client(api_key=api_key)

        # Model to use (gemini-2.0-flash-exp or gemini-2.5-flash)
        self.model_name = 'gemini-2.0-flash-exp'

        logger.info("Gemini client initialized successfully")

    def generate_summary(self, messages: List[Dict]) -> str:
        """
        Generate conversation summary from messages

        Args:
            messages: List of message dicts with 'author', 'content', 'timestamp'

        Returns:
            Summary text

        Raises:
            Exception: If API call fails
        """
        if not messages:
            logger.warning("No messages provided for summary generation")
            return "No messages to summarize."

        try:
            # Format messages for the prompt
            formatted_messages = self._format_messages_for_prompt(messages)

            # Create the prompt
            prompt = self._create_prompt(formatted_messages, len(messages))

            # Generate summary with the new SDK
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.3,  # Lower for more factual summaries
                    top_p=0.8,
                    top_k=40,
                    max_output_tokens=1024,
                )
            )

            # Extract and return text
            summary = response.text
            logger.info(f"Successfully generated summary for {len(messages)} messages")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary with Gemini: {e}", exc_info=True)
            raise

    def _format_messages_for_prompt(self, messages: List[Dict]) -> str:
        """
        Format messages for inclusion in the prompt

        Args:
            messages: List of message dicts with 'author', 'content', 'timestamp'

        Returns:
            Formatted message string
        """
        formatted = []

        for msg in messages:
            timestamp = msg['timestamp'].strftime('%Y-%m-%d %H:%M')
            author = msg['author']
            content = msg['content']

            # Skip empty messages
            if not content.strip():
                continue

            formatted.append(f"[{timestamp}] {author}: {content}")

        return "\n".join(formatted)

    def _create_prompt(self, formatted_messages: str, message_count: int) -> str:
        """
        Create the full prompt for Gemini

        Args:
            formatted_messages: Pre-formatted message string
            message_count: Number of messages

        Returns:
            Complete prompt string
        """
        prompt = f"""You are analyzing a Discord conversation for moderation purposes. You will be provided with {message_count} messages from a conversation thread.

**Instructions:**
1. Identify the main topics discussed
2. Summarize key points and conclusions
3. Note any significant contributions by participants
4. Include author names for context and accountability
5. Keep summary concise (maximum 500 words)
6. Format as markdown with bullet points
7. Ignore any off-topic or irrelevant messages or side-conversations if you deem them irrelevant to the main discussion

**Messages:**
{formatted_messages}

**Summary:**
Please provide a structured summary following this format:

## Main Topics
- [Topic 1]
- [Topic 2]

## Key Points
- [Point 1 with relevant author names]
- [Point 2 with relevant author names]

## Notable Contributions
- [Author name]: [Their contribution]

Keep the summary professional and objective, suitable for moderation review."""

        return prompt
