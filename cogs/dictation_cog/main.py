"""Dictation cog — audio listening exercises for language practice."""

import io
import logging

import aioboto3
import discord
from discord import Interaction, app_commands
from discord.ext import commands

from base_cog import BaseCog
from config import get_str_env

from .config import ANSWER_TIMEOUT_SECONDS, MAX_SCORE, S3_BUCKET, S3_REGION
from .scoring import score_answer

logger = logging.getLogger(__name__)

_AWS_KEY = get_str_env("AWS_ACCESS_KEY_ID", "")
_AWS_SECRET = get_str_env("AWS_SECRET_ACCESS_KEY", "")

LANG_CHOICES = [
    app_commands.Choice(name="🇪🇸 Spanish", value="es"),
    app_commands.Choice(name="🇬🇧 English", value="en"),
]
LEVEL_CHOICES = [
    app_commands.Choice(name="🟢 Beginner", value="beginner"),
    app_commands.Choice(name="🟡 Intermediate+", value="intermediate"),
]

_SCORE_EMOJI = {0: "😢", 1: "😕", 2: "🙂", 3: "😊", 4: "🎉"}


class DictationCog(BaseCog):
    """Audio dictation exercises — listen and type what you hear."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self._session = aioboto3.Session(
            aws_access_key_id=_AWS_KEY,
            aws_secret_access_key=_AWS_SECRET,
        )
        # channel_id -> (sentence_id, expected_text, user_id)
        self._pending: dict[int, tuple[int, str, int]] = {}
        logger.info("DictationCog loaded")

    @app_commands.command(name="dictation", description="Listen to a sentence and type what you hear!")
    @app_commands.describe(
        language="Language to practice",
        level="Difficulty level",
    )
    @app_commands.choices(language=LANG_CHOICES, level=LEVEL_CHOICES)
    async def dictation(
        self,
        interaction: Interaction,
        language: app_commands.Choice[str],
        level: app_commands.Choice[str],
    ) -> None:
        channel_id = interaction.channel_id
        user_id = interaction.user.id

        if channel_id in self._pending:
            await interaction.response.send_message(
                "⏳ There's already a dictation in progress in this channel. "
                "Type your answer or wait for it to time out.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        sentence = await self.bot.db.get_random_dictation(
            language.value, level.value, user_id,
        )
        if not sentence:
            await interaction.followup.send("❌ No sentences available for that combination.")
            return

        # Fetch audio from S3
        audio_bytes = await self._fetch_audio(sentence["audio_url"])
        if not audio_bytes:
            await interaction.followup.send("❌ Could not load audio file. Try again later.")
            return

        self._pending[channel_id] = (sentence["id"], sentence["sentence"], user_id)

        lang_flag = "🇪🇸" if language.value == "es" else "🇬🇧"
        file = discord.File(io.BytesIO(audio_bytes), filename="dictation.mp3")
        await interaction.followup.send(
            f"{lang_flag} **Dictation** ({level.name})\n"
            f"🎧 Listen and type what you hear! You have {ANSWER_TIMEOUT_SECONDS}s.",
            file=file,
        )

        logger.info(
            "Dictation started by %s in #%s (%s, %s, sentence_id=%s)",
            interaction.user, channel_id, language.value, level.value, sentence["id"],
        )

        # Wait for answer
        def check(m: discord.Message) -> bool:
            return m.channel.id == channel_id and m.author.id == user_id and not m.author.bot

        try:
            msg = await self.bot.wait_for("message", check=check, timeout=ANSWER_TIMEOUT_SECONDS)
        except TimeoutError:
            self._pending.pop(channel_id, None)
            await interaction.channel.send("⏰ Time's up! The correct sentence was:\n"
                                           f">>> {sentence['sentence']}")
            return

        self._pending.pop(channel_id, None)
        user_answer = msg.content.strip()

        score, corrections = score_answer(sentence["sentence"], user_answer)

        await self.bot.db.record_dictation_score(user_id, sentence["id"], score, user_answer)

        embed = self._build_result_embed(score, sentence["sentence"], user_answer, corrections)
        await msg.reply(embed=embed)

        logger.info(
            "Dictation scored %s/%s for %s in #%s (sentence_id=%s)",
            score, MAX_SCORE, interaction.user, channel_id, sentence["id"],
        )

    async def _fetch_audio(self, audio_url: str) -> bytes | None:
        """Download an MP3 from S3."""
        try:
            async with self._session.client("s3", region_name=S3_REGION) as s3:
                resp = await s3.get_object(Bucket=S3_BUCKET, Key=audio_url)
                return await resp["Body"].read()
        except Exception:
            logger.exception("Failed to fetch audio: %s", audio_url)
            return None

    def _build_result_embed(
        self, score: int, expected: str, actual: str, corrections: list[dict],
    ) -> discord.Embed:
        """Build the result embed showing score and corrections."""
        emoji = _SCORE_EMOJI.get(score, "")
        color = [0xE74C3C, 0xE67E22, 0xF1C40F, 0x2ECC71, 0x27AE60][score]

        embed = discord.Embed(
            title=f"{emoji} Score: {score}/{MAX_SCORE}",
            color=color,
        )
        embed.add_field(name="✅ Correct sentence", value=expected, inline=False)
        embed.add_field(name="✏️ Your answer", value=actual or "*(empty)*", inline=False)

        if corrections:
            lines = []
            for c in corrections[:10]:  # cap at 10
                if c["type"] == "accent":
                    lines.append(f"• **{c['expected']}** → {c['actual']} *(accent)*")
                elif c["type"] == "typo":
                    lines.append(f"• **{c['expected']}** → {c['actual']} *(typo)*")
                elif c["type"] == "missing":
                    lines.append(f"• **{c['expected']}** *(missing)*")
                elif c["type"] == "extra":
                    lines.append(f"• ~~{c['actual']}~~ *(extra)*")
                else:
                    lines.append(f"• **{c['expected']}** → {c['actual']}")
            embed.add_field(name="📝 Corrections", value="\n".join(lines), inline=False)
        elif score == MAX_SCORE:
            embed.add_field(name="📝", value="Perfect! No corrections needed.", inline=False)

        return embed


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DictationCog(bot))
