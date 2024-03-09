from base_cog import COLORS as colors

from os import path, walk
from random import choice
from csv import reader

from discord import Embed, File

dir_path = path.dirname(path.dirname(path.realpath(__file__)))

ENDED = "Ahorcado (Hangman) - {} - Partida terminada"
WINNER = "¡Ganaste, **{}**! La palabra correcta era **{}** ({})"
LOSER = "Perdiste jeje. La palabra correcta era **{}** ({})"

ACENTOS = {
    'á': 'a',
    'é': 'e',
    'í': 'i',
    'ó': 'o',
    'ú': 'u',
    'ü': 'u',
}


def get_unaccented_word(word: str) -> str:
    no_accent = [ACENTOS[letter] if letter in ACENTOS else letter for letter in word]

    return ''.join(no_accent)


def get_unaccented_letter(letter):
    if letter in ACENTOS:
        return ACENTOS[letter]
    return letter


def get_word(category):
    with open(f"{dir_path}/hangman_data/{category}.csv", "r", encoding='utf 8') as animals_csv:
        result = reader(animals_csv)
        words = (choice(list(result)))
    return words[0], words[1]


def get_image(img, category):
    for root, _, files in walk(f"{dir_path}/hangman_data/{category}_images/{img}"):
        ani = [[f"{root}/{file}", f"{file}"] for file in files]
        return choice(ani)


# returns hidden string with space(s)
def get_hidden_word(word):
    return [' ' if s == ' ' else '◯' for s in word]  # faster than regex sub('[^\s]', '◯', string)


# new hangman
def start_game(word):
    return f"""
    `{' '.join(word)}`
    . ┌─────┐
    .┃...............┋
    .┃...............┋
    .┃
    .┃
    .┃ 
    /-\\
    """


def get_hangman_string(errors, message="", correctly_guest="", wrongly_guessed=""):
    back_slash = "\\"  # can't use back_slash in f-string
    return f"""
    {message}
    `{' '.join(correctly_guest)}`
    . ┌─────┐
    .┃...............┋
    .┃...............┋
    .┃{".............:cry:" if errors > 1 else ""}
    .┃{"............./" if errors > 3 else ""} {"|" if errors > 4 else ""} {back_slash if errors > 5 else ""} 
    .┃{"............./" if errors > 6 else ""} {back_slash if errors > 7 else ""}
    /-\\    
    {' '.join(wrongly_guessed)}
    """


def embed_quote(header, state):
    embed = Embed(color=choice(colors))
    embed.title = header
    embed.description = state
    return embed


def create_final_embed(winner, words, category, result):
    # TODO:
    # put image links in a database/csv file
    if category == 'ciudades':
        category_image = get_image(words[0], category)
    else:
        category_image = get_image(words[1].replace(' ', ''), category)
    file = File(category_image[0], filename=category_image[1])
    embed = Embed(color=choice(colors))
    embed.title = ENDED.format(category)
    embed.description = WINNER.format(winner, words[0], words[1]) if result else LOSER.format(words[0],
                                                                                              words[1])
    embed.set_image(url=f"attachment://{category_image[1]}")
    return file, embed
