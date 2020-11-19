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

from typing import List

from tabulate import tabulate

from nucypher.policy.identity import Card


def paint_single_card(emitter, card: Card, qrcode: bool = False) -> None:
    emitter.echo('*'*90)
    emitter.message(f'{card.nickname.capitalize() or str(card.character.__name__)}\'s Card ({card.id.hex()})')
    encrypting_key = card.encrypting_key.hex()
    verifying_key = card.verifying_key.hex()
    emitter.echo(f'Encrypting Key - {encrypting_key}')
    emitter.echo(f'Verifying Key - {verifying_key}')
    if qrcode:
        card.to_qr_code()
    emitter.echo('*'*90)


def paint_cards(emitter, cards: List[Card], as_table: bool = True) -> None:
    if as_table:
        rows = [card.describe() for card in cards]
        emitter.echo(tabulate(rows, headers='keys', showindex='always', tablefmt="presto"))
    else:
        for card in cards:
            paint_single_card(emitter=emitter, card=card)
