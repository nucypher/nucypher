"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import json
from typing import List
import random
from os.path import abspath, dirname, join


_HERE = abspath(dirname(__file__))
with open(join(_HERE, 'web_colors.json')) as f:
    _COLORS = json.load(f)['colors']

_SYMBOLS = {
    "A": "Alfa",
    "B": "Bravo",
    "C": "Charlie",
    "D": "Delta",
    "E": "Echo",
    "F": "Foxtrot",
    "G": "Golf",
    "H": "Hotel",
    "I": "India",
    "J": "Juliett",
    "K": "Kilo",
    "L": "Lima",
    "M": "Mike",
    "N": "November",
    "O": "Oscar",
    "P": "Papa",
    "Q": "Quebec",
    "R": "Romeo",
    "S": "Sierra",
    "T": "Tango",
    "U": "Uniform",
    "V": "Victor",
    "W": "Whiskey",
    "X": "X-ray",
    "Y": "Yankee",
    "Z": "Zulu",
    "0": "Zero",
    "1": "One",
    "2": "Two",
    "3": "Three",
    "4": "Four",
    "5": "Five",
    "6": "Six",
    "7": "Seven",
    "8": "Eight",
    "9": "Nine",
}


class NicknameCharacter:

    def __init__(self, symbol: str, color_name: str, color_hex: str):
        self.symbol = symbol
        self.color_name = color_name
        self.color_hex = color_hex
        self._text = color_name + " " + _SYMBOLS[symbol]

    def to_json(self):
        return dict(symbol=self.symbol,
                    color_name=self.color_name,
                    color_hex=self.color_hex)

    def __str__(self):
        return self._text


class Nickname:

    @classmethod
    def from_seed(cls, seed, length: int = 2):
        # TODO: #1823 - Workaround for new nickname every restart
        # if not seed:
        #     raise ValueError("No checksum provided to derive nickname.")
        rng = random.Random(seed)
        nickname_symbols = rng.sample(list(_SYMBOLS), length)
        nickname_colors = rng.sample(_COLORS, length)
        characters = [
            NicknameCharacter(symbol, color['color'], color['hex'])
            for symbol, color in zip(nickname_symbols, nickname_colors)]
        return cls(characters)

    def __init__(self, characters: List[NicknameCharacter]):
        self._text = " ".join(str(character) for character in characters)
        self.icon = "[" + "".join(character.symbol for character in characters) + "]"
        self.characters = characters

    def to_json(self):
        return dict(text=self._text,
                    icon=self.icon,
                    characters=[character.to_json() for character in self.characters])

    def __str__(self):
        return self._text
