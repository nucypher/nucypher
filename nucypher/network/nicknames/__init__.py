import json
import random
from os.path import abspath, dirname, join

HERE = BASE_DIR = abspath(dirname(__file__))
with open(join(HERE, 'web_colors.json')) as f:
    colors = json.load(f)

with open(join(HERE, 'zodiac.json')) as f:
    zodiac = json.load(f)

eastern = zodiac['eastern_zodiac']
western = zodiac['western_zodiac']

eastern_list = list(eastern.keys())
western_list = list(western.keys())

colors = colors['colors']
pairs = []


def nickname_from_seed(seed):
    random.seed(seed)
    color1 = random.choice(colors)
    color2 = random.choice(colors)
    western_symbol = random.choice(western_list)
    eastern_symbol = random.choice(eastern_list)
    nickname = "{}ish {} {} {}".format(color1['color'], color2['color'], western_symbol, eastern_symbol)
    nickname_metadata = (color1, color2, western[western_symbol], eastern[eastern_symbol])
    return nickname, nickname_metadata
