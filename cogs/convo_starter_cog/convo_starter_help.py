import csv
import os
import random

categories = ['general', 'phil', 'would', 'other']

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))

def get_random_question(category: str) -> tuple:
    with open(f"{dir_path}/convo_starter_cog/convo_starter_data/{category}.csv") as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        rows = [(row[0], row[1]) for row in csv_reader]
    spa, eng = random.choice(rows)
    return spa, eng
