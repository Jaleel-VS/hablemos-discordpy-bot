from dataclasses import dataclass
from typing import Optional, Tuple
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


@dataclass
class GameResult:
    """Represents the result of a hangman game."""
    player_name: str
    word: str
    definition: str
    category: str
    won: bool
    
    @property
    def display_word(self) -> str:
        """Get the word to display in the image filename."""
        if self.category == 'ciudades':
            return self.word
        return self.definition.replace(' ', '')


def get_unaccented_word(word: str) -> str:
    no_accent = [ACENTOS[letter] if letter in ACENTOS else letter for letter in word]

    return ''.join(no_accent)


def get_unaccented_letter(letter: str) -> str:
    if letter in ACENTOS:
        return ACENTOS[letter]
    return letter


def get_word(category):
    with open(f"{dir_path}/hangman_cog/data/{category}.csv", "r", encoding='utf 8') as animals_csv:
        result = reader(animals_csv)
        words = (choice(list(result)))
    return words[0], words[1]


def get_image(img: str, category: str) -> Optional[Tuple[str, str]]:
    """
    Get a random image file for the given word and category.
    
    Args:
        img: The word/image name to search for
        category: The category (animales, ciudades, profesiones)
        
    Returns:
        Tuple of (file_path, filename) or None if not found
    """
    image_dir = f"{dir_path}/hangman_cog/data/{category}_images/{img}"
    
    if not path.exists(image_dir):
        return None
        
    try:
        for root, _, files in walk(image_dir):
            if files:
                file_paths = [(f"{root}/{file}", file) for file in files]
                return choice(file_paths)
    except (OSError, IndexError):
        pass
    
    return None


def _create_embed_content(result: GameResult) -> Tuple[str, str]:
    """Create the title and description for the final embed."""
    title = ENDED.format(result.category)
    
    if result.won:
        description = WINNER.format(result.player_name, result.word, result.definition)
    else:
        description = LOSER.format(result.word, result.definition)
    
    return title, description


def _get_fallback_embed(result: GameResult) -> Embed:
    """Create a fallback embed when no image is available."""
    embed = Embed(color=choice(colors))
    title, description = _create_embed_content(result)
    embed.title = title
    embed.description = description
    return embed


def create_final_embed(player_name: str, words: list[str], category: str, won: bool) -> Tuple[Optional[File], Embed]:
    """
    Create the final embed for a completed hangman game.
    
    Args:
        player_name: Name of the player who made the final guess
        words: List containing [word, definition]
        category: Game category (animales, ciudades, profesiones)
        won: True if player won, False if they lost
        
    Returns:
        Tuple of (Discord File or None, Discord Embed)
    """
    # Validate input
    if len(words) < 2:
        raise ValueError(f"Words list must contain at least 2 elements, got {len(words)}")
    
    # Create result object for better organization
    result = GameResult(
        player_name=player_name,
        word=words[0],
        definition=words[1],
        category=category,
        won=won
    )
    
    # Try to get an image
    image_data = get_image(result.display_word, category)
    
    if image_data is None:
        # Return embed without image
        return None, _get_fallback_embed(result)
    
    # Create embed with image
    file_path, filename = image_data
    file = File(file_path, filename=filename)
    
    embed = Embed(color=choice(colors))
    title, description = _create_embed_content(result)
    embed.title = title
    embed.description = description
    embed.set_image(url=f"attachment://{filename}")
    
    return file, embed


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
