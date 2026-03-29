"""Conversation starter question helpers."""
import csv
import random
from pathlib import Path

categories = ['general', 'phil', 'would', 'other']

DATA_DIR = Path(__file__).resolve().parent / "convo_starter_data"


def get_random_question(category: str) -> tuple:
    """Return a random (spanish, english) question pair from the given category."""
    with open(DATA_DIR / f"{category}.csv") as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        rows = [(row[0], row[1]) for row in csv_reader]
    spa, eng = random.choice(rows)
    return spa, eng
