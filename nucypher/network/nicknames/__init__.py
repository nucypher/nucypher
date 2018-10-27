import json
import random
from os.path import abspath, dirname, join

HERE = BASE_DIR = abspath(dirname(__file__))
with open(join(HERE, 'web_colors.json')) as f:
    colors = json.load(f)

with open(join(HERE, 'zodiac.json')) as f:
    zodiac = json.load(f)

colors = colors['colors']
pairs = []

zodiac_signs = zodiac['eastern_zodiac']
zodiac_signs.update(zodiac['western_zodiac'])


def nickname_from_seed(seed):
    random.seed(seed)
    color1 = random.choice(colors)
    color2 = random.choice(colors)

    zodiac_list = list(zodiac_signs.keys())

    symbol1 = random.choice(zodiac_list)
    zodiac_list.remove(symbol1)
    symbol2 = random.choice(zodiac_list)
    nickname = "{} {} {} {}".format(color1['color'], symbol1, color2['color'], symbol2)
    nickname_metadata = (color1, zodiac_signs[symbol1], color2, zodiac_signs[symbol2])
    return nickname, nickname_metadata
