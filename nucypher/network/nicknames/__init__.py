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

import unicodedata

HERE = BASE_DIR = abspath(dirname(__file__))
with open(join(HERE, 'web_colors.json')) as f:
    colors = json.load(f)

colors = colors['colors']
pairs = []

symbols_tuple = ("♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓",
                 "♚", "♛", "♜", "♝", "♞", "♟", "⚓", "⚔", "⚖", "⚗", "⚑", "⚘",
                 "⚪", "⚵", "⚿", "⛇", "⛈", "⛰", "⛸", "⛴", "⛨", "✈", "☤",
                 "⏚", "☠", "☸", "☿", "☾", "♁", "♃", "♄", "☄", "☘", "⚜", "⚚",
                 "⏲", "☣", "☥", "♣", "♥", "♦", "♠", "♫", "⚝", "⚛", "⚙", "⎈",
                 "☮", "☕", "☈", "♯", "♭")

def nicename(symbol):
    unicode_name = unicodedata.name(symbol)
    final_word = unicode_name.split()[-1]
    if final_word in ("SYMBOL", "SUIT", "SIGN"):
        final_word = unicode_name.split()[-2]
    return final_word.capitalize()


def nickname_from_seed(seed, number_of_pairs=2):
    symbols = list(symbols_tuple)

    random.seed(seed)
    pairs = []
    for pair in range(number_of_pairs):
        color = random.choice(colors)
        symbol = random.choice(symbols)
        symbols.remove(symbol)
        pairs.append((color, symbol))
    nickname = " ".join(("{} {}".format(c['color'], nicename(s)) for c, s in pairs))
    return nickname, pairs
