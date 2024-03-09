import asyncio
from re import sub

from discord.ext.commands import Cog

from cogs.hangman_cog.hangman_help import (get_unaccented_letter,
                                                get_unaccented_word,
                                                get_hidden_word,
                                                get_hangman_string,
                                                embed_quote,
                                                create_final_embed,
                                                start_game
                                                )

# strings for the embeds
DOES_NOT_EXIST = "{} La `{}` no se encuentra en esta palabra. Puedes volver a adivinar en 2 segundos"
ALREADY_GUESSED = "{} La `{}` ya se ha adivinado . Puedes volver a adivinar en 2 segundos"
CORRECT_GUESS = "{} ha adivinado la letra `{}`"
STARTED = "Nueva partida - **{}**"
ON_GOING = "Ahorcado (Hangman) - **{}**"
TIME_OUT = "La sesión ha expirado"
SPA_ALPHABET = "aábcdeéfghiíjklmnñoópqrstuúüvwxyz"
VOWELS = {'a': ['a', 'á'],
          'e': ['e', 'é'],
          'i': ['i', 'í'],
          'o': ['o', 'ó'],
          'u': ['u', 'ú', 'ü'], }
MAX_ERRORS = 8


class Hangman(Cog):
    def __init__(self, bot, words, category):
        self.bot = bot
        self.category = category
        self.words = words
        self.original_word = sub('/(.*)', '', words[0].lower())
        self.unaccented_word = get_unaccented_word(self.original_word)
        self.hidden_word = get_hidden_word(self.original_word)
        self.original_word_list = list(self.original_word)
        self.unaccented_word_list = list(self.unaccented_word)
        self.hidden_word_list = list(self.hidden_word)
        self.errors = 0
        self.indices = {letter: [] for letter in self.unaccented_word}
        self.letters_found = set()
        self.players = {}
        self.correctly_guessed = None
        self.embed_quote = embed_quote
        self.embedded_message = ""

    async def game_loop(self, ctx):
        print(f"New game started - {self.category} - {self.words}")
        self.create_dict_indices()

        await ctx.send(embed=self.embed_quote(STARTED.format(self.category),
                                              start_game(self.hidden_word_list)))

        while self.game_in_progress():
            user_guess: tuple = await self.get_user_guess(ctx)

            if not user_guess[0]:  # if it returns False the input timed out
                break
            # elif not self.is_input_valid(user_guess[1]):
            #     continue

            player_id, player_name, player_input = self.get_input_info(user_guess[1])

            if await self.did_user_quit(player_input, ctx):
                break

            if len(player_input) == 1:
                self.update_single_letter(get_unaccented_letter(player_input))
            else:
                self.hidden_word_list = self.original_word_list

            await self.send_embed(ctx, player_name, player_input)

    def game_in_progress(self):
        return (
                self.hidden_word_list
                not in (self.unaccented_word_list, self.original_word_list)
                and not self.max_errors_reached()
        )

    def create_dict_indices(self):
        for idx, letter in enumerate(self.unaccented_word):
            self.indices[letter].append(idx)

    async def get_user_guess(self, context):
        def is_input_valid(user_message):
            message_content = user_message.content.strip().lower()
            message_in_command_channel = user_message.channel == context.channel
            message_is_valid = message_content in SPA_ALPHABET or message_content in ('quit',
                                                                                      self.original_word,
                                                                                      self.unaccented_word)
            user_is_not_bot = not user_message.author.bot
            return message_in_command_channel and message_is_valid and user_is_not_bot

        try:
            user_input = ""
            user_input = await self.bot.wait_for('message',
                                                 check=is_input_valid,
                                                 timeout=45)
        except asyncio.TimeoutError:
            await context.send(TIME_OUT)
            return False, ""

        return True, user_input

    @staticmethod
    def get_input_info(message):
        user_id = message.author.id
        user_name = message.author
        user_guess = message.content.strip().lower()

        return user_id, user_name, user_guess

    @staticmethod
    async def did_user_quit(user_guess, context):
        if user_guess == 'quit':
            await context.send('Partida terminada')
            return True

    def update_single_letter(self, player_input):
        input_found = player_input in self.indices
        input_unique = player_input not in self.letters_found

        if input_found and input_unique:
            self.replace_hidden_character(self.indices[player_input])
            self.extend_found_set(player_input)
            self.embedded_message = CORRECT_GUESS
        elif not input_unique:
            self.errors += 1
            self.embedded_message = ALREADY_GUESSED
        else:
            self.extend_found_set(player_input)
            self.errors += 1
            self.embedded_message = DOES_NOT_EXIST

    def replace_hidden_character(self, indices):
        for i in indices:
            self.hidden_word_list[i] = self.original_word_list[i]

    async def send_embed(self, context, name_, input_):
        if self.max_errors_reached():
            await self.send_final_embed(context, name_, False)
        elif not self.word_found():
            await context.send(embed=self.embed_quote(
                ON_GOING.format(self.category),
                get_hangman_string(
                    self.errors,
                    self.embedded_message.format(
                        name_,
                        '/'.join(VOWELS[input_]) if input_ in VOWELS else input_,
                    ),
                    self.hidden_word_list,
                    self.letters_found

                ),
            ))
        else:
            await self.send_final_embed(context, name_, True)

    def extend_found_set(self, letter):
        self.letters_found.update(VOWELS[letter] if letter in VOWELS else letter)

    async def send_final_embed(self, context, name_, result):
        end_embed = create_final_embed(name_, self.words, self.category, result)
        await context.send(file=end_embed[0], embed=end_embed[1])

    def word_found(self):
        return self.original_word_list == self.hidden_word_list

    def max_errors_reached(self):
        return self.errors == MAX_ERRORS
