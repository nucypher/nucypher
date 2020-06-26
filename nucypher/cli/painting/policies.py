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

from nucypher.policy.identity import Card


def paint_single_card(emitter, card: Card) -> None:
    card_dict = card.to_json(as_string=False)
    emitter.echo('*'*30)
    emitter.message(f'{card}')
    for field, value in card_dict.items():
        emitter.echo(f'{field} ... {value}')
    emitter.echo('*'*30)


def paint_cards(emitter, cards: List[Card]) -> None:
    for card in cards:
        paint_single_card(emitter=emitter, card=card)
    # card_dict = card.to_dict()
    # headers = [field for field in Card._specification]
    # rows = [[n] for n in NetworksInventory.NETWORKS]
    # emitter.echo(tabulate(rows, headers=headers, showindex='always'))
