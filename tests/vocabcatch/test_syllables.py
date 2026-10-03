"""Spanish syllable splitting + stress used by the anniversary card typography."""
import pytest

from cogs.vocabcatch_cog.syllables import stressed_index, syllabify


@pytest.mark.parametrize(("word", "expected", "stress"), [
    # plain CV words and the RAE default stress (llana / aguda)
    ("casa", ["ca", "sa"], 0),
    ("mariposa", ["ma", "ri", "po", "sa"], 2),
    ("comer", ["co", "mer"], 1),
    ("atardecer", ["a", "tar", "de", "cer"], 3),
    # written accent wins
    ("relámpago", ["re", "lám", "pa", "go"], 1),
    ("crepúsculo", ["cre", "pús", "cu", "lo"], 1),
    ("efímero", ["e", "fí", "me", "ro"], 1),
    # digraphs stay whole
    ("perro", ["pe", "rro"], 0),
    ("calle", ["ca", "lle"], 0),
    ("chico", ["chi", "co"], 0),
    ("susurrar", ["su", "su", "rrar"], 2),
    # silent u in qu/gu, diaeresis keeps it
    ("queso", ["que", "so"], 0),
    ("guitarra", ["gui", "ta", "rra"], 1),
    ("pingüino", ["pin", "güi", "no"], 1),
    ("inquietud", ["in", "quie", "tud"], 2),
    # diphthongs vs hiatus
    ("cuervo", ["cuer", "vo"], 0),
    ("ciudad", ["ciu", "dad"], 1),
    ("agua", ["a", "gua"], 0),
    ("día", ["dí", "a"], 0),
    ("reír", ["re", "ír"], 1),
    ("aéreo", ["a", "é", "re", "o"], 1),
    # y as vowel only at the end / before a consonant
    ("rey", ["rey"], 0),
    ("ayer", ["a", "yer"], 1),
    ("estoy", ["es", "toy"], 1),
    # consonant clusters: inseparable pairs move together
    ("hombre", ["hom", "bre"], 0),
    ("hablar", ["ha", "blar"], 1),
    ("instante", ["ins", "tan", "te"], 1),
    ("abstracto", ["abs", "trac", "to"], 1),
    ("construir", ["cons", "truir"], 1),
    ("inefable", ["i", "ne", "fa", "ble"], 2),
    # h between vowels is a consonant
    ("prohibir", ["pro", "hi", "bir"], 2),
])
def test_syllabify_and_stress(word: str, expected: list[str], stress: int) -> None:
    assert syllabify(word) == expected
    assert stressed_index(expected) == stress


def test_syllabify_preserves_case() -> None:
    assert syllabify("Mariposa") == ["Ma", "ri", "po", "sa"]


@pytest.mark.parametrize("word", ["", "darse cuenta", "sh"])
def test_unsplittable_input_returns_whole(word: str) -> None:
    assert syllabify(word) == [word]
