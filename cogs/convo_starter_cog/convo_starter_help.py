import csv
import os
from random import randint

categories = ['general', 'phil', 'would', 'other']

dir_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def get_random_question(category: str) -> tuple:
    with open(f"{dir_path}/convo_starter_cog/convo_starter_data/{category}.csv") as csv_file:
        csv_reader = csv.reader(csv_file, delimiter=',')
        spa_q = []
        eng_q = []
        rows = 0
        for row in csv_reader:
            spa_q.append(row[0])
            eng_q.append(row[1])
            rows += 1
    random_num = randint(0, rows + 1)
    return spa_q[random_num], eng_q[random_num]
