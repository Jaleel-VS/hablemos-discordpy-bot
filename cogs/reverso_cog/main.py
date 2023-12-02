from cogs.reverso_cog.helper import HelperFunctions
from base_cog import BaseCog

from discord.ext import commands
from discord.ext.commands import command, cooldown, BucketType
# from discord.ext.commands import Paginator
from reverso_api.context import ReversoContextAPI as reverso
from discord import Embed  # , Color, ButtonStyle

NOT_FOUND_ERROR = "Input not recognised. Please type `$langcodes` to see a list of available languages. " \
                  "Please type `$help reverso` too see correct example usage."
REVERSO_URL = "https://context.reverso.net/translation/"

helper_functions = HelperFunctions()


class Reverso(BaseCog):
    """Fetch example sentences from the Reverso Context API given user input"""
    def __init__(self, bot):
        super().__init__(bot)
        self.languages = []
        self.user_input = ""

    @command(aliases=['rev', 'reverse', ])
    @cooldown(1, 10, type=BucketType.user)
    async def reverso(self, ctx: commands.Context, lang_original=None, lang_target=None, *, message=None):
        """
        (still experimental, please report any bugs or errors)
        Receive in-context examples of a specific text in your target language
        - `reverso <source_language_code> <target_language_code> <message>`
        examples:
            - `reverso en es the booking process was`
            - `-reverso de nl die frau`

        see `$langcodes` for a list of language codes

        The bot doesn't check for spelling so if you don't see any or few results,
        please make sure the input is spelled correctly
        """
        if not await self.is_input_valid(ctx, lang_original, lang_target, message):
            return

        ctx_message = await ctx.send(embed=Embed(color=0xf47fff,  # nitro pink
                                                 description="<a:loading:925770299188867105> Please wait"))

        self.languages = [lang_original, lang_target]
        self.user_input = message
        reverso_entries, results_found = self.get_entries(lang_original, lang_target, message)
        await ctx_message.delete()
        if results_found:
            reverso_pages = self.get_pages(reverso_entries)
            # reverso_paginator = self.get_paginator(reverso_pages)
            # await reverso_paginator.send(ctx, ephemeral=False)
            await ctx.send(embed=reverso_pages[0])  # temporary until fix paginator
        else:
            await ctx.send(f"No results found. Please check your language codes and or spelling. "
                           f"Feel free to also checkout :\n{REVERSO_URL}")

    @staticmethod
    async def is_input_valid(context, lang_original, lang_target, message):
        valid = True
        if (
            lang_original not in helper_functions.language_codes
            or lang_target not in helper_functions.language_codes
        ):
            await context.send(NOT_FOUND_ERROR)
            valid = False

        elif message is None:
            await context.send("Please enter the text you want translated\n eg. `$reverso es en lo que hicimos`")
            valid = False

        return valid

    @staticmethod
    def get_entries(lang_1, lang_2, input_string):
        api = reverso(input_string, "", lang_1, lang_2)
        examples = []
        for counter, (source_lang, target_lang) in enumerate(api.get_examples()):
            example = [helper_functions.highlight_example(source_lang.text, source_lang.highlighted),
                       helper_functions.highlight_example(target_lang.text, target_lang.highlighted)]
            examples.append(example)
            if counter == 9:  # get ten examples
                break

        if not examples:
            return [[]], False
        else:
            return examples, True

    def get_pages(self, entries):
        return [self.result_embed(entry) for entry in entries]

    def result_embed(self, entry):
        embed = Embed(color=0xf47fff)  # nitro pink
        url = self.get_source_url()
        embed.description = f"<:reverso:925746938379386882> {helper_functions.language_codes[self.languages[0]]} -> " \
                            f"{helper_functions.language_codes[self.languages[1]]}\n"
        embed.title = f"{self.user_input.lower()}"
        embed.add_field(name=self.languages[0], value=entry[0], inline=False)
        embed.add_field(name=self.languages[1], value=entry[1], inline=False)
        embed.add_field(name="\u200b", value=f"[See original page on ReversoContext]({url})", inline=False)
        return embed

    # @staticmethod
    # def get_paginator(embedded_pages):
    #     paginator = Paginator(pages=embedded_pages, show_disabled=False, show_indicator=True)
    #     paginator.customize_button("next", button_label=">", button_style=ButtonStyle.green)
    #     paginator.customize_button("prev", button_label="<", button_style=ButtonStyle.green)
    #     paginator.customize_button("first", button_label="<<", button_style=ButtonStyle.blurple)
    #     paginator.customize_button("last", button_label=">>", button_style=ButtonStyle.blurple)
    #     return paginator

    def get_source_url(self):
        return (
            f"{REVERSO_URL}{helper_functions.language_codes[self.languages[0]].lower()}-"
            f"{helper_functions.language_codes[self.languages[1]].lower()}/{'+'.join(self.user_input.split())}"
        )

    @command(aliases=['lc', 'codes'])
    async def langcodes(self, ctx):
        language_codes = "".join(
            f"- {code}: {lang}\n"
            for code, lang in helper_functions.language_codes.items()
        )

        await ctx.send(embed=Embed(color=0xf47fff,  # nitro pink
                                   description=language_codes))


async def setup(bot):
    await bot.add_cog(Reverso(bot))
