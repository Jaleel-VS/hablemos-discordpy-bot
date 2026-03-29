from discord import Color, Embed, Interaction, app_commands
from discord.ext import commands
from discord.ext.commands import Bot, command

from base_cog import BaseCog
from cogs.utils.embeds import green_embed

try:
    from cogs.league_cog.config import ROUNDS
except ImportError:
    # Fallback if league cog not available
    class ROUNDS:
        ROUND_DURATION_DAYS = 14

SOURCE_URL = 'https://docs.google.com/spreadsheets/d/10jsNQsSG9mbLZgDoYIdVrbogVSN7eAKbOfCASA5hN0A/edit?usp=sharing'
REPO = 'https://github.com/Jaleel-VS/hablemos-discordpy-bot'
DPY = 'https://discordpy.readthedocs.io/en/latest/'
PYC = 'https://github.com/Pycord-Development/pycord'
INVITE_LINK = "https://discord.com/api/oauth2/authorize?client_id=808377026330492941&permissions=3072&scope=bot"


class General(BaseCog):
    def __init__(self, bot: Bot):
        super().__init__(bot)

    @app_commands.command(name="help", description="View all available bot commands and features")
    @app_commands.describe(category="Choose a specific category to view")
    @app_commands.choices(category=[
        app_commands.Choice(name="📚 All Commands", value="all"),
        app_commands.Choice(name="🗣️ Conversation & Learning", value="conversation"),
        app_commands.Choice(name="📝 Vocabulary & Study", value="vocabulary"),
        app_commands.Choice(name="🎮 Games & Fun", value="games"),
        app_commands.Choice(name="🏆 Language League", value="league"),
        app_commands.Choice(name="🎵 Social Features", value="social"),
        app_commands.Choice(name="🛠️ Moderation & Admin", value="admin")
    ])
    async def help_slash(self, interaction: Interaction, category: str = "all"):
        """Comprehensive help command showing all bot features"""

        if category == "all":
            embed = Embed(
                title="🤖 Hablemos Bot - Command Guide",
                description=(
                    "A comprehensive language learning bot for Spanish and English learners!\n\n"
                    "**Select a category below or use `/help <category>` for details:**"
                ),
                color=Color.blue()
            )

            embed.add_field(
                name="🗣️ Conversation & Learning",
                value=(
                    "`/convo` - Generate AI conversations\n"
                    "`/conjugate` - Practice verb conjugations\n"
                    "`/synonyms` - Find synonyms & antonyms"
                ),
                inline=False
            )

            embed.add_field(
                name="📝 Vocabulary & Study",
                value=(
                    "`/vocab add` - Save vocabulary notes\n"
                    "`/vocab list` - View your notes\n"
                    "`/vocab search` - Search your vocabulary\n"
                    "`/vocab delete` - Remove a note\n"
                    "`/vocab export` - Export to CSV"
                ),
                inline=False
            )

            embed.add_field(
                name="🎮 Games & Fun",
                value=(
                    "`$hangman` - Play hangman\n"
                    "`$topic` - Conversation starters\n"
                    "`$quote` - Random quotes"
                ),
                inline=False
            )

            embed.add_field(
                name="🏆 Language League",
                value=(
                    "`/league join` - Join the competition\n"
                    "`/league view` - See rankings\n"
                    "`/league stats` - Your progress\n"
                    "`/league leave` - Opt out"
                ),
                inline=False
            )

            embed.add_field(
                name="🎵 Social Features",
                value=(
                    "`/spotify` - Share what you're listening to\n"
                    "`$info` - Bot information\n"
                    "`$ping` - Check bot latency"
                ),
                inline=False
            )

            embed.add_field(
                name="🛠️ Moderation & Admin",
                value=(
                    "`$summarize` - Summarize conversations\n"
                    "`$intro` - Introduction tracking\n"
                    "`$note` - Database commands\n"
                    "*Owner-only commands available*"
                ),
                inline=False
            )

            embed.set_footer(text="Use /help <category> for detailed information about each category")

        elif category == "conversation":
            embed = Embed(
                title="🗣️ Conversation & Learning Commands",
                description="AI-powered conversation generation and language practice tools",
                color=Color.green()
            )

            embed.add_field(
                name="/convo",
                value=(
                    "Generate AI conversations for language practice.\n"
                    "**Daily limit:** 10 conversations per user\n"
                    "**Features:** Customizable scenarios, realistic dialogues"
                ),
                inline=False
            )

            embed.add_field(
                name="/conjugate <verb> [tense]",
                value=(
                    "Practice verb conjugations in Spanish.\n"
                    "**Supported tenses:** Present, Preterite, Imperfect, Future, and more\n"
                    "**Example:** `/conjugate hablar present`"
                ),
                inline=False
            )

            embed.add_field(
                name="/synonyms <word> <language>",
                value=(
                    "Find synonyms and antonyms for any word.\n"
                    "**Languages:** Spanish, English\n"
                    "**Example:** `/synonyms happy english`"
                ),
                inline=False
            )

        elif category == "vocabulary":
            embed = Embed(
                title="📝 Vocabulary & Study Commands",
                description="Save, manage, and review your vocabulary notes privately",
                color=Color.gold()
            )

            embed.add_field(
                name="/vocab add",
                value=(
                    "Add a new vocabulary note (ephemeral - private to you).\n"
                    "Opens a form where you can enter:\n"
                    "• Word or phrase\n"
                    "• Translation/definition\n"
                    "• Language (optional)"
                ),
                inline=False
            )

            embed.add_field(
                name="/vocab list [limit]",
                value=(
                    "View your saved vocabulary notes.\n"
                    "**Default:** Shows 10 most recent notes\n"
                    "**Max:** 50 notes per page"
                ),
                inline=False
            )

            embed.add_field(
                name="/vocab search <query>",
                value=(
                    "Search through your vocabulary notes.\n"
                    "Searches in words, translations, and language fields."
                ),
                inline=False
            )

            embed.add_field(
                name="/vocab delete <note_id>",
                value=(
                    "Delete a specific note by ID.\n"
                    "You can find note IDs using `/vocab list`"
                ),
                inline=False
            )

            embed.add_field(
                name="/vocab export",
                value=(
                    "Export all your notes to a CSV file.\n"
                    "Perfect for importing into flashcard apps!"
                ),
                inline=False
            )

        elif category == "games":
            embed = Embed(
                title="🎮 Games & Fun Commands",
                description="Interactive games and conversation tools",
                color=Color.purple()
            )

            embed.add_field(
                name="$hangman",
                value=(
                    "Classic hangman game for vocabulary practice.\n"
                    "Guess letters to reveal the hidden word!"
                ),
                inline=False
            )

            embed.add_field(
                name="$topic [category]",
                value=(
                    "Get conversation starter questions.\n"
                    "**Categories:** general (1), philosophical (2), would you rather (3), other (4)\n"
                    "**Example:** `$topic phil`"
                ),
                inline=False
            )

            embed.add_field(
                name="$quote",
                value="Get a random inspirational quote.",
                inline=False
            )

        elif category == "league":
            embed = Embed(
                title="🏆 Language League Commands",
                description="Compete with other learners and track your progress!",
                color=Color.orange()
            )

            embed.add_field(
                name="How It Works",
                value=(
                    "• **Choose ONE language** to focus on (Spanish OR English)\n"
                    "• **Write messages** in that language (min 10 characters)\n"
                    "• **Earn points** for quality language practice\n"
                    "• **Get bonuses** for consistency (+5 points per active day)\n"
                    "• **Compete** in biweekly rounds (2 weeks each)\n"
                    "• **Win awards** - #1 winners get a star ⭐"
                ),
                inline=False
            )

            embed.add_field(
                name="/league join",
                value=(
                    "Join the Language League competition.\n"
                    "**Requirements:**\n"
                    "• Must have ONE Learning role (Spanish OR English)\n"
                    "• Cannot be native in language you're learning\n"
                    "• Only messages in your learning language count"
                ),
                inline=False
            )

            embed.add_field(
                name="/league view [spanish|english|combined] [limit]",
                value=(
                    "View league rankings.\n"
                    "**Spanish League:** Spanish learners only\n"
                    "**English League:** English learners only\n"
                    "**Combined League:** All participants"
                ),
                inline=False
            )

            embed.add_field(
                name="/league stats [@user]",
                value=(
                    "View your stats or another user's stats.\n"
                    "Shows: Total points, active days, score, rankings"
                ),
                inline=False
            )

            embed.add_field(
                name="/league leave",
                value="Opt out of the Language League (preserves historical data).",
                inline=False
            )

            embed.add_field(
                name="📊 Scoring System",
                value=(
                    "**Points:** 1 point per valid message\n"
                    "**Consistency Bonus:** +5 points per active day\n"
                    "**Total Score:** Points + (Active Days × 5)\n\n"
                    "**Anti-Spam:**\n"
                    "• 2-minute cooldown per channel\n"
                    "• 50 message daily cap\n"
                    "• Language detection (must be in target language)"
                ),
                inline=False
            )

        elif category == "social":
            embed = Embed(
                title="🎵 Social Features",
                description="Share and connect with the community",
                color=Color.teal()
            )

            embed.add_field(
                name="/spotify",
                value=(
                    "Share what you're currently listening to on Spotify.\n"
                    "Shows: Song, artist, album, and link"
                ),
                inline=False
            )

            embed.add_field(
                name="$info",
                value="Get information about the bot and development.",
                inline=False
            )

            embed.add_field(
                name="$ping",
                value="Check the bot's latency and response time.",
                inline=False
            )

        elif category == "admin":
            embed = Embed(
                title="🛠️ Moderation & Admin Commands",
                description="Tools for server moderators and administrators",
                color=Color.red()
            )

            embed.add_field(
                name="$summarize <message_count> [#channel]",
                value=(
                    "Summarize recent conversation using AI.\n"
                    "**Max:** 100 messages\n"
                    "*Moderator only*"
                ),
                inline=False
            )

            embed.add_field(
                name="Introduction Tracking",
                value=(
                    "Tracks user introductions and exemptions.\n"
                    "`$intro exempt <@user>` - Add exemption\n"
                    "`$intro unexempt <@user>` - Remove exemption\n"
                    "*Admin only*"
                ),
                inline=False
            )

            embed.add_field(
                name="Database Commands",
                value=(
                    "`$note add <@user> <note>` - Add user note\n"
                    "`$note view <@user>` - View user notes\n"
                    "`$note delete <note_id>` - Delete note\n"
                    "*Admin only*"
                ),
                inline=False
            )

            embed.add_field(
                name="League Admin Commands",
                value=(
                    "`$league ban <@user>` - Ban from league\n"
                    "`$league unban <@user>` - Unban from league\n"
                    "`$league exclude <#channel>` - Exclude channel\n"
                    "`$league include <#channel>` - Include channel\n"
                    "`$league excluded` - List excluded channels\n"
                    "`$league admin_stats` - View league statistics\n"
                    "`$league endround` - End round & start new one\n"
                    "`$league preview` - Preview round-end announcement\n"
                    "`$league seedrole <ids>` - Seed role recipients\n"
                    "*Owner only*"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @command()
    async def help(self, ctx, arg=''):
        if arg:
            # Special handling for league
            if arg.lower() == 'league':
                # Calculate round duration display
                days = ROUNDS.ROUND_DURATION_DAYS
                if days == 7:
                    duration_text = "week"
                elif days == 14:
                    duration_text = "2 weeks"
                elif days % 7 == 0:
                    duration_text = f"{days // 7} weeks"
                else:
                    duration_text = f"{days} days"

                league_embed = Embed(
                    title="🏆 Language League",
                    description=(
                        "**Practice your target language. Compete. Win.**\n\n"
                        "The Language League rewards consistent practice in Spanish or English. "
                        "Every message you write in your target language earns points. "
                        "Stay active, climb the rankings, and show your dedication!\n\n"
                        f"🔁 **Rounds:** Every {duration_text}\n"
                        f"🎯 **Focus:** Write in your target language to earn points\n"
                        f"⭐ **Rewards:** Top 3 winners each round get recognition\n\n"
                    ),
                    color=Color.gold()
                )

                league_embed.add_field(
                    name="⚡ Quick Start",
                    value=(
                        "**1.** Use `/league join` to opt in\n"
                        "**2.** Start writing messages in your target language\n"
                        "**3.** Check `/league view` to see rankings\n"
                        "**4.** Track your progress with `/league stats`"
                    ),
                    inline=False
                )

                league_embed.set_footer(
                    text="💬 Use /league commands | Questions? Message/tag the bot owner"
                )

                await ctx.send(embed=league_embed)
                return

            # Default command lookup
            requested = self.bot.get_command(arg)
            if not requested:
                await ctx.send("I was unable to find the command you requested")
                return
            message = ""
            message += f"**{self.bot.command_prefix}{requested.qualified_name}**\n"
            if requested.aliases:
                message += f"Aliases: `{'`, `'.join(requested.aliases)}`\n"
            if requested.help:
                message += requested.help
            emb = green_embed(message)
            await ctx.send(embed=emb)
        else:
            to_send = f"""
            Type `{self.bot.command_prefix}help <command>` for more info about on any command.
            ⚠️ If something doesn't work as expected, it's expected lol. I'm currently refactoring the bot, please be patient.
            """
            await ctx.send(embed=green_embed(to_send))

    @command(aliases=['list', ])
    async def lst(self, ctx):
        """
        Lists available categories
        """
        categories = f"""
        To use any one of the undermentioned topics type `$topic <category>`.
        `$topic` or `$top` defaults to `general`

        command(category) - description:
        `general`, `1` - General questions
        `phil`, `2` - Philosophical questions
        `would`, `3` - *'Would you rather'* questions
        `other`, `4` -  Random questions

        [Full list of questions]({SOURCE_URL})
        """
        await ctx.send(embed=green_embed(categories))

    @command()
    async def info(self, ctx):
        """
        Information about the bot
        """

        text = f"""
        The bot was coded in Python using the [discord.py]({DPY}) framework. Possible future migration to a C# or Rust framework

        To report an error or make a suggestion please message <@216848576549093376>
        [Github Repository]({REPO})
        """

        await ctx.send(embed=green_embed(text))

    @command()
    async def invite(self, ctx):
        """
        Bot invitation link
        """

        text = f"""
        [Invite the bot to your server]({INVITE_LINK})
        I still have to make the prefix configurable so for now you have to use `$`
        """

        await ctx.send(embed=green_embed(text))

    @command()
    async def ping(self, ctx):
        """
        Ping the bot to see if there are latency issues
        """
        await ctx.send(embed=green_embed(f"**Command processing time**: {round(self.bot.latency * 1000, 2)}ms"))

    @command()
    @commands.is_owner()
    async def mystats(self, ctx):
        """Show servers the bot is in. Owner only."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        lines = []
        for g in guilds:
            joined = g.me.joined_at
            joined_str = f"<t:{int(joined.timestamp())}:R>" if joined else "?"
            lines.append(f"**{g.name}** — {g.member_count:,} members, joined {joined_str}")

        embed = Embed(
            title=f"Servers ({len(guilds)})",
            description='\n'.join(lines) or "Not in any servers.",
            color=Color.blurple(),
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(General(bot))
