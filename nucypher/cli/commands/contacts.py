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

import click
import os
import shutil

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.select import select_card
from nucypher.cli.options import option_force
from nucypher.cli.painting.policies import paint_single_card, paint_cards
from nucypher.cli.types import EXISTING_READABLE_FILE, UMBRAL_PUBLIC_KEY_HEX
from nucypher.policy.identity import Card

id_option = click.option('--id', 'card_id', help="A single card's checksum or ID", type=click.STRING, required=False)
type_option = click.option('--type', 'character_flag', help="Type of card: (A)lice or (B)ob.", type=click.STRING, required=False)
verifying_key_option = click.option('--verifying-key', help="Alice's or Bob's verifying key as hex", type=click.STRING, required=False)
encrypting_key_option = click.option('--encrypting-key', help="An encrypting key as hex", type=click.STRING, required=False)
nickname_option = click.option('--nickname', help="Human-readable nickname / alias for a card", type=click.STRING, required=False)


@click.group()
def contacts():
    """Lightweight contacts utility to store public keys of known ("character cards") Alices and Bobs."""


@contacts.command()
@click.argument('query')
@click.option('--qrcode', help="Display the QR code representing a card to the console", is_flag=True, default=None)
def show(query, qrcode):
    """
    Lookup and view existing character card
    QUERY can be either the card id or nickname.
    """
    emitter = StdoutEmitter()
    try:
        card = select_card(emitter=emitter, card_identifier=query)
    except Card.UnknownCard as e:
        return emitter.error(str(e))
    paint_single_card(emitter=emitter, card=card, qrcode=qrcode)


@contacts.command('list')
def _list():
    """Show all character cards"""
    emitter = StdoutEmitter()
    card_directory = Card.CARD_DIR
    try:
        card_filepaths = os.listdir(card_directory)
    except FileNotFoundError:
        os.mkdir(Card.CARD_DIR)
        card_filepaths = os.listdir(card_directory)
    if not card_filepaths:
        emitter.error(f'No cards found at {card_directory}.  '
                      f"To create one run 'nucypher {contacts.name} {create.name}'.")
    cards = list()
    for filename in card_filepaths:
        card = Card.load(filepath=Card.CARD_DIR / filename)
        cards.append(card)
    paint_cards(emitter=emitter, cards=cards, as_table=True)


@contacts.command()
@type_option
@encrypting_key_option
@verifying_key_option
@nickname_option
@option_force
def create(character_flag, verifying_key, encrypting_key, nickname, force):
    """Store a new character card"""
    emitter = StdoutEmitter()

    # Validate
    if not all((character_flag, verifying_key, encrypting_key)) and force:
        emitter.error(f'--verifying-key, --encrypting-key, and --type are required with --force enabled.')

    # Card type
    from constant_sorrow.constants import ALICE, BOB
    flags = {'a': ALICE, 'b': BOB}
    if not character_flag:
        choice = click.prompt('Enter Card Type - (A)lice or (B)ob', type=click.Choice(['a', 'b'], case_sensitive=False))
        character_flag = flags[choice]
    else:
        character_flag = flags[character_flag]

    # Verifying Key
    if not verifying_key:
        verifying_key = click.prompt('Enter Verifying Key', type=UMBRAL_PUBLIC_KEY_HEX)
    verifying_key = bytes.fromhex(verifying_key)  # TODO: Move / Validate

    # Encrypting Key
    if character_flag is BOB:
        if not encrypting_key:
            encrypting_key = click.prompt('Enter Encrypting Key', type=UMBRAL_PUBLIC_KEY_HEX)
        encrypting_key = bytes.fromhex(encrypting_key)  # TODO: Move / Validate

    # Init
    new_card = Card(character_flag=character_flag,
                    verifying_key=verifying_key,
                    encrypting_key=encrypting_key,
                    nickname=nickname)

    # Nickname
    if not force and not nickname:
        card_id_hex = new_card.id.hex()
        nickname = click.prompt('Enter nickname for card', default=card_id_hex)
        if nickname != card_id_hex:  # not the default
            nickname = nickname.strip()
            new_card.nickname = nickname

    # Save
    new_card.save()
    emitter.message(f'Saved new card {new_card}', color='green')
    paint_single_card(emitter=emitter, card=new_card)


@contacts.command()
@id_option
@option_force
def delete(force, card_id):
    """Delete an existing character card."""
    emitter = StdoutEmitter()
    card = select_card(emitter=emitter, card_identifier=card_id)
    if not force:
        click.confirm(f'Are you sure you want to delete {card}?', abort=True)
    card.delete()
    emitter.message(f'Deleted card for {card.id.hex()}.', color='red')


@contacts.command()
@click.option('--filepath', help="System filepath of stored card to import", type=EXISTING_READABLE_FILE)
def import_card(filepath):
    """Import a character card from a card file"""
    emitter = StdoutEmitter()
    shutil.copy(filepath, Card.CARD_DIR)
    # paint_single_card(card=card)
    emitter.message(f'Successfully imported card.')
