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


from tabulate import tabulate
from typing import List

from nucypher.characters.lawful import Bob
from nucypher.policy.identity import Card


def paint_single_card(emitter, card: Card, qrcode: bool = False) -> None:
    emitter.echo('*'*90, color='cyan')
    emitter.message(f'{(card.nickname or str(card.character.__name__)).capitalize()}\'s Card (ID {card.id.hex()})', bold=True)
    emitter.echo(f'Verifying Key - {card.verifying_key.hex()}')
    if card.character is Bob:
        emitter.echo(f'Encrypting Key - {card.encrypting_key.hex()}')
    if qrcode:
        card.to_qr_code()
    emitter.echo('*'*90, color='cyan')


def paint_cards(emitter, cards: List[Card], as_table: bool = True) -> None:
    if as_table:
        rows = [card.describe() for card in cards]
        emitter.echo(tabulate(rows, headers='keys', showindex='always', tablefmt="presto"))
    else:
        for card in cards:
            paint_single_card(emitter=emitter, card=card)
