import asyncio
from re import sub
import logging

from discord.ext.commands import Cog

from cogs.hangman_cog.hangman_help import (get_unaccented_letter,
                                                get_unaccented_word,
                                                get_hidden_word,
                                                get_hangman_string,
                                                embed_quote,
                                                create_final_embed,
                                                start_game
                                                )

# Set up logger for this module
logger = logging.getLogger(__name__)

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
        self.players = {}  # Track players: user_id -> {"name": str, "guesses": int}
        self.game_starter = None  # Track who started the game
        self.correctly_guessed = None
        self.embed_quote = embed_quote
        self.embedded_message = ""
        
        logger.debug(f"Hangman game initialized: word='{self.original_word}', category='{category}', definition='{words[1] if len(words) > 1 else 'N/A'}'")

    async def game_loop(self, ctx):
        logger.info(f"Game loop starting for word '{self.original_word}' in category '{self.category}' in channel {ctx.channel.id}")
        self.game_starter = ctx.author.id  # Remember who started the game
        self.create_dict_indices()

        await ctx.send(embed=self.embed_quote(STARTED.format(self.category),
                                              start_game(self.hidden_word_list)))

        turn_count = 0
        while self.game_in_progress():
            turn_count += 1
            logger.debug(f"Turn {turn_count} starting - Errors: {self.errors}/{MAX_ERRORS}, Progress: {''.join(self.hidden_word_list)}")
            
            user_guess: tuple = await self.get_user_guess(ctx)

            if not user_guess[0]:  # if it returns False the input timed out
                logger.info(f"Game timed out after {turn_count} turns")
                break

            user_id, player_name, player_input = self.get_input_info(user_guess[1])
            
            # Track player participation
            if user_id not in self.players:
                self.players[user_id] = {"name": str(player_name), "guesses": 0}
                logger.info(f"New player joined: {player_name} ({user_id})")
            
            self.players[user_id]["guesses"] += 1
            
            logger.debug(f"Turn {turn_count}: {player_name} ({user_id}) guessed '{player_input}'")

            if await self.did_user_quit(player_input, ctx, user_id):
                logger.info(f"Game quit by {player_name} ({user_id})")
                break

            if len(player_input) == 1:
                self.update_single_letter(get_unaccented_letter(player_input))
            else:
                logger.info(f"{player_name} guessed the full word: '{player_input}'")
                self.hidden_word_list = self.original_word_list

            await self.send_embed(ctx, player_name, player_input)
            
            # Log game state after each turn
            if self.word_found():
                logger.info(f"Game won by {player_name} after {turn_count} turns!")
                break
            elif self.max_errors_reached():
                logger.info(f"Game lost after {turn_count} turns - max errors reached")
                break
        
        # Log final game statistics
        total_players = len(self.players)
        total_guesses = sum(p["guesses"] for p in self.players.values())
        logger.info(f"Game ended: {total_players} players, {total_guesses} total guesses, {self.errors} errors")

    def game_in_progress(self):
        return (
                self.hidden_word_list != self.unaccented_word_list
                and self.hidden_word_list != self.original_word_list
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

    async def did_user_quit(self, user_guess, context, user_id):
        """Check if user quit the game. Only the game starter can quit."""
        if user_guess == 'quit':
            if user_id == self.game_starter:
                logger.info(f"Game quit by starter (user {user_id})")
                await context.send('Partida terminada')
                return True
            else:
                logger.debug(f"Quit attempt by non-starter user {user_id} - ignored")
                await context.send('⚠️ Solo quien inició la partida puede terminarla.')
                return False
        return False

    def update_single_letter(self, player_input):
        input_found = player_input in self.indices
        input_unique = player_input not in self.letters_found

        logger.debug(f"Letter '{player_input}': found={input_found}, unique={input_unique}")

        if input_found and input_unique:
            self.replace_hidden_character(self.indices[player_input])
            self.extend_found_set(player_input)
            self.embedded_message = CORRECT_GUESS
            logger.debug(f"Correct guess! Letter '{player_input}' found at positions {self.indices[player_input]}")
        elif not input_unique:
            self.errors += 1
            self.embedded_message = ALREADY_GUESSED
            logger.debug(f"Letter '{player_input}' already guessed. Errors: {self.errors}")
        else:
            self.extend_found_set(player_input)
            self.errors += 1
            self.embedded_message = DOES_NOT_EXIST
            logger.debug(f"Letter '{player_input}' not in word. Errors: {self.errors}")

    def replace_hidden_character(self, indices):
        for i in indices:
            self.hidden_word_list[i] = self.original_word_list[i]
        logger.debug(f"Updated hidden word: {''.join(self.hidden_word_list)}")

    async def send_embed(self, context, name_, input_):
        if self.max_errors_reached():
            logger.info("Game lost - max errors reached")
            await self.send_final_embed(context, name_, False)
        elif not self.word_found():
            logger.debug("Game continues - sending game state embed")
            await context.send(embed=self.embed_quote(
                ON_GOING.format(self.category),
                get_hangman_string(
                    self.errors,
                    self.embedded_message.format(
                        name_,
                        '/'.join(VOWELS[input_]) if input_ in VOWELS else input_,
                    ),
                    ' '.join(self.hidden_word_list),
                    ' '.join(sorted(self.letters_found))

                ),
            ))
        else:
            logger.info(f"Game won by {name_}!")
            await self.send_final_embed(context, name_, True)

    def extend_found_set(self, letter):
        before_size = len(self.letters_found)
        self.letters_found.update(VOWELS[letter] if letter in VOWELS else letter)
        after_size = len(self.letters_found)
        logger.debug(f"Letters found updated: {before_size} -> {after_size} letters")

    async def send_final_embed(self, context, name_, result):
        logger.info(f"Sending final embed - Winner: {name_ if result else 'None'}, Word: {self.original_word}")
        end_embed = create_final_embed(name_, self.words, self.category, result)
        await context.send(file=end_embed[0], embed=end_embed[1])

    def word_found(self):
        return self.original_word_list == self.hidden_word_list

    def max_errors_reached(self):
        return self.errors == MAX_ERRORS
