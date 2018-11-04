"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
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
