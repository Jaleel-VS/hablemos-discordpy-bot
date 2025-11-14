"""
Synonyms and Antonyms Cog for Spanish words using WordReference
"""
import logging
import discord
from discord.ext import commands
from base_cog import BaseCog, COLORS
from .wordreference_parser import WordReferenceParser
from .cache import SynonymCache
import random

logger = logging.getLogger(__name__)


class SynonymsCog(BaseCog):
    """Cog for looking up Spanish synonyms and antonyms"""

    def __init__(self, bot):
        super().__init__(bot)
        self.parser = WordReferenceParser()
        self.cache = SynonymCache(ttl_seconds=86400)  # 24 hour cache

    @commands.command(name='sinonimos', aliases=['sin', 'syn', 'synonyms'])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def synonyms(self, ctx, *, word: str):
        """
        Look up synonyms and antonyms for a Spanish word

        Usage:
          !sinonimos juntar
          !sin hablar
          !syn ser

        Data source: WordReference.com
        """
        if not word or len(word.strip()) == 0:
            await ctx.send("Por favor, proporciona una palabra para buscar.")
            return

        # Clean the word
        word = word.strip().lower()

        # Send a "searching" message
        searching_msg = await ctx.send(f"🔍 Buscando sinónimos para **{word}**...")

        try:
            # Check cache first
            data = self.cache.get(word)
            from_cache = data is not None

            if not data:
                # Not in cache, fetch from WordReference
                data = self.parser.fetch_word(word)

                # Store in cache if found
                if data:
                    self.cache.set(word, data)

            if not data:
                # Word not found
                embed = discord.Embed(
                    title="No encontrado",
                    description=f"No se encontraron sinónimos para **{word}**.",
                    color=0xED4245  # Red
                )
                embed.add_field(
                    name="Sugerencias",
                    value="• Verifica la ortografía\n• Intenta con una forma diferente de la palabra\n• Asegúrate de que sea una palabra en español",
                    inline=False
                )
                # Edit the searching message instead of sending new one
                await searching_msg.edit(content=f"{ctx.author.mention}", embed=embed)
                return

            # Create embed with results
            embed = discord.Embed(
                title=f"**{data['word']}**",
                url=data['url'],
                color=random.choice(COLORS)
            )

            # Add synonym groups
            if data['synonym_groups']:
                for i, group in enumerate(data['synonym_groups'], 1):
                    # Limit to first 10 synonyms per group to avoid too long messages
                    display_synonyms = group[:15]
                    more_count = len(group) - len(display_synonyms)

                    synonym_text = ", ".join(display_synonyms)
                    if more_count > 0:
                        synonym_text += f" *[+{more_count} más]*"

                    field_name = "Sinónimos" if i == 1 and len(data['synonym_groups']) == 1 else f"Sinónimos ({i})"
                    embed.add_field(
                        name=field_name,
                        value=synonym_text,
                        inline=False
                    )
            else:
                embed.add_field(
                    name="Sinónimos",
                    value="*No se encontraron sinónimos*",
                    inline=False
                )

            # Add antonym groups
            if data['antonym_groups']:
                for i, group in enumerate(data['antonym_groups'], 1):
                    # Limit to first 10 antonyms per group
                    display_antonyms = group[:15]
                    more_count = len(group) - len(display_antonyms)

                    antonym_text = ", ".join(display_antonyms)
                    if more_count > 0:
                        antonym_text += f" *[+{more_count} más]*"

                    field_name = "Antónimos" if i == 1 and len(data['antonym_groups']) == 1 else f"Antónimos ({i})"
                    embed.add_field(
                        name=field_name,
                        value=antonym_text,
                        inline=False
                    )

            # Add stats in footer
            syn_count = self.parser.get_synonym_count(data)
            ant_count = self.parser.get_antonym_count(data)
            footer_text = f"{syn_count} sinónimo(s)"
            if ant_count > 0:
                footer_text += f" • {ant_count} antónimo(s)"
            if from_cache:
                footer_text += " • 💾 Caché"
            else:
                footer_text += " • WordReference.com"
            embed.set_footer(text=footer_text)

            # Edit the searching message with results and ping user
            await searching_msg.edit(content=f"{ctx.author.mention}", embed=embed)

        except Exception as e:
            logger.error(f"Error in synonyms command for word '{word}': {e}", exc_info=True)

            # Edit searching message with error
            embed = discord.Embed(
                title="Error",
                description=f"Ocurrió un error al buscar **{word}**. Por favor, intenta de nuevo más tarde.",
                color=0xED4245
            )
            try:
                await searching_msg.edit(content=f"{ctx.author.mention}", embed=embed)
            except:
                # If editing fails, send a new message
                await ctx.send(embed=embed)

    @commands.command(name='antonimos', aliases=['ant', 'antonyms'])
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def antonyms(self, ctx, *, word: str):
        """
        Look up antonyms for a Spanish word (also shows synonyms)

        Usage:
          !antonimos juntar
          !ant separar

        Data source: WordReference.com
        """
        # This is essentially the same as synonyms, but with a different alias
        # We'll just call the synonyms command
        await ctx.invoke(self.bot.get_command('sinonimos'), word=word)

    @commands.command(name='sinonimos_help', aliases=['sin_help'])
    async def synonyms_help(self, ctx):
        """Show help for synonym/antonym commands"""
        prefix = self.bot.command_prefix if isinstance(self.bot.command_prefix, str) else '!'

        embed = discord.Embed(
            title="Ayuda de Sinónimos y Antónimos",
            description="Busca sinónimos y antónimos de palabras en español usando WordReference.com",
            color=0x57F287
        )

        embed.add_field(
            name="Comandos",
            value=f"""
            `{prefix}sinonimos <palabra>` - Buscar sinónimos y antónimos
            `{prefix}sin <palabra>` - Atajo para sinonimos
            `{prefix}antonimos <palabra>` - Buscar antónimos (igual que sinonimos)
            `{prefix}ant <palabra>` - Atajo para antonimos
            """,
            inline=False
        )

        embed.add_field(
            name="Ejemplos",
            value=f"""
            `{prefix}sin hablar` - Sinónimos de "hablar"
            `{prefix}sinonimos juntar` - Sinónimos de "juntar"
            `{prefix}ant separar` - Antónimos de "separar"
            """,
            inline=False
        )

        embed.add_field(
            name="Notas",
            value="""
            • Los resultados pueden incluir múltiples grupos de sinónimos para diferentes significados
            • Los datos provienen de WordReference.com (Diccionario Espasa-Calpe)
            • Los resultados se guardan en caché por 24 horas
            • Cooldown: 1 búsqueda cada 15 segundos por usuario
            """,
            inline=False
        )

        embed.set_footer(text="Fuente: WordReference.com")
        await ctx.send(embed=embed)

    @commands.command(name='sinonimos_stats', aliases=['sin_stats'])
    @commands.is_owner()
    async def synonyms_stats(self, ctx):
        """Show cache statistics (bot owner only)"""
        stats = self.cache.get_stats()

        embed = discord.Embed(
            title="📊 Estadísticas de Caché - Sinónimos",
            color=0x3498db
        )

        embed.add_field(
            name="Uso del Caché",
            value=f"""
            **Tamaño:** {stats['size']} entradas
            **Solicitudes totales:** {stats['total_requests']}
            **Aciertos:** {stats['hits']} ({stats['hit_rate']:.1f}%)
            **Fallos:** {stats['misses']}
            """,
            inline=False
        )

        embed.add_field(
            name="Operaciones",
            value=f"""
            **Almacenados:** {stats['stores']}
            **Desalojos:** {stats['evictions']}
            """,
            inline=False
        )

        # Calculate efficiency message
        if stats['hit_rate'] >= 50:
            efficiency = "🟢 Excelente"
        elif stats['hit_rate'] >= 30:
            efficiency = "🟡 Bueno"
        else:
            efficiency = "🟠 Normal"

        embed.add_field(
            name="Eficiencia",
            value=efficiency,
            inline=False
        )

        embed.set_footer(text="TTL: 24 horas")
        await ctx.send(embed=embed)

    @commands.command(name='sinonimos_clear_cache', aliases=['sin_clear'])
    @commands.is_owner()
    async def clear_cache(self, ctx):
        """Clear the synonym cache (bot owner only)"""
        count = self.cache.clear()
        await ctx.send(f"✅ Caché limpiado. Se eliminaron {count} entradas.")


async def setup(bot):
    await bot.add_cog(SynonymsCog(bot))
