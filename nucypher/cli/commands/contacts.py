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

import shutil

import click
import os

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.select import select_card
from nucypher.cli.options import option_force
from nucypher.cli.painting.policies import paint_single_card, paint_cards
from nucypher.cli.types import EXISTING_READABLE_FILE
from nucypher.policy.identity import Card


@click.group()
def contacts():
    """"Manage character cards"""


@contacts.command()
@click.option('--id', 'card_id', type=click.STRING, required=False)
@click.option('--qrcode', is_flag=True, default=None)
def lookup(card_id, qrcode):
    """"Manage character cards"""
    emitter = StdoutEmitter()
    card = select_card(emitter=emitter, card_id=card_id)
    paint_single_card(emitter=emitter, card=card, qrcode=qrcode)


@contacts.command()
def all():
    emitter = StdoutEmitter()
    card_filepaths = os.listdir(Card.CARD_DIR)
    if not card_filepaths:
        emitter.error('No cards found.')
    cards = list()
    for filename in card_filepaths:
        card_id, ext = filename.split('.')
        card = Card.load(checksum=card_id)
        cards.append(card)
    paint_cards(emitter=emitter, cards=cards, as_table=True)


@contacts.command()
@click.option('--id', 'card_id', type=click.STRING, required=False)
@click.option('--type', 'character_flag', type=click.STRING, required=False)
@click.option('--verifying-key', type=click.STRING, required=False)
@click.option('--encrypting-key', type=click.STRING, required=False)
@click.option('--nickname', type=click.STRING, required=False)
def create(emitter, card_id, character_flag, verifying_key, encrypting_key, nickname, force):
    emitter = StdoutEmitter()

    if not all((character_flag, verifying_key, encrypting_key)) and force:
        emitter.error(f'--verifying-key, --encrypting-key, and --type are required with --force enabled.')
    if not force and not nickname:
        nickname = click.prompt('Enter Card Nickname')
    if not character_flag:
        from constant_sorrow.constants import ALICE, BOB
        choice = click.prompt('Enter Card Type - (A)lice or (B)ob', type=click.Choice(['a', 'b'], case_sensitive=False))
        flags = {'a': ALICE, 'b': BOB}
        character_flag = flags[choice]
    if not verifying_key:
        verifying_key = click.prompt('Enter Verifying Key', type=click.STRING)
    verifying_key = bytes.fromhex(verifying_key)  # TODO: Move / Validate
    if not encrypting_key:
        encrypting_key = click.prompt('Enter Encrypting Key', type=click.STRING)
    encrypting_key = bytes.fromhex(encrypting_key)  # TODO: Move / Validate

    new_card = Card(character_flag=character_flag,
                    verifying_key=verifying_key,
                    encrypting_key=encrypting_key,
                    nickname=nickname)
    new_card.save()
    emitter.message(f'Saved new card {new_card}', color='green')
    paint_single_card(emitter=emitter, card=new_card)


@contacts.command()
@click.option('--id', 'card_id', type=click.STRING, required=False)
@option_force
def delete(force, card_id):
    emitter = StdoutEmitter()
    card = select_card(emitter=emitter, card_id=card_id)
    if not force:
        click.confirm(f'Are you sure you want to delete {card}?', abort=True)
    card.delete()
    emitter.message(f'Deleted card.', color='red')


@contacts.command()
@click.option('--filepath', type=EXISTING_READABLE_FILE)
def import_card(filepath):
    emitter = StdoutEmitter()
    shutil.copy(filepath, Card.CARD_DIR)
    # paint_single_card(card=card)
    emitter.message(f'Successfully imported card.')
