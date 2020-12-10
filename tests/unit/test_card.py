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

import pytest

from nucypher.characters.lawful import Bob, Alice
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.policy.identity import Card
from tests.utils.middleware import MockRestMiddleware


@pytest.mark.parametrize('character_class', (Bob, Alice))
def test_character_card(character_class):
    character = character_class(federated_only=True,
                                start_learning_now=False,
                                network_middleware=MockRestMiddleware())

    character_card = character.get_card()
    same_card = Card.from_character(character)
    assert character_card == same_card

    with pytest.raises(TypeError):
        # only cards can be compared to other cards
        _ = character_card == same_card.verifying_key

    # Bob's Keys
    assert character_card.verifying_key == character.public_keys(SigningPower)
    assert character_card.encrypting_key == character.public_keys(DecryptingPower)

    # Card Serialization

    # bytes
    card_bytes = bytes(character_card)
    assert Card.from_bytes(card_bytes) == character_card == same_card

    # hex
    hex_bob = character_card.to_hex()
    assert Card.from_hex(hex_bob) == character_card == same_card

    # base64
    base64_bob = character_card.to_base64()
    assert Card.from_base64(base64_bob) == character_card == same_card

    # qr code echo
    character_card.to_qr_code()
    # TODO: Examine system output here?

    # nicknames
    original_checksum = character_card.id
    nickname = 'Wilson'
    character_card.set_nickname(nickname)
    restored = Card.from_bytes(bytes(character_card))
    restored_checksum = restored.id
    assert restored.nickname == nickname
    assert original_checksum == restored_checksum == same_card.id
