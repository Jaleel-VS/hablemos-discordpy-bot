import sqlite3

# Sqlite3 tables dictionary
tables = {'general': 'generales', 'personal': 'personales', 'tv': 'televisión', 'movies': 'películas',
          'books': 'libros', "music": 'música',
          'tech': 'tecnología', 'sport': 'deportes', 'food': 'comida_cocina', 'travel': 'viajes', 'fashion': 'ropa',
          'holi': 'feriados', 'edu': 'educación', 'strange': 'extrañas', 'phil': 'filo', 'lang': 'idiomas',
          'games': 'juegos', 'open': 'open'}

tables_keys = list(tables.keys())
tables_first_two_characters = [key[0:2] for key in tables_keys]
tables_values = list(tables.values())

# SQLITE QUERY
connection = sqlite3.connect("cogs/utils/preguntas.db")
"""
SQLITE QUERY TO GET RANDOM QUESTION FROM SPECIFIED TABLE
{0} - English or Spanish question
{1} - topic/category
"""

SELECT_RANDOM_QUESTION = """
SELECT * FROM {0}
ORDER BY RANDOM()
LIMIT 1;
"""

def random_question(table):
    if table in tables_values:
        with connection:
            cursor = connection.cursor()
            cursor.execute(SELECT_RANDOM_QUESTION.format(table))
        return cursor.fetchone()
    return
