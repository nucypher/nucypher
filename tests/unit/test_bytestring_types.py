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
from bytestring_splitter import BytestringSplitter, BytestringSplittingError

from nucypher.characters.lawful import Enrico
from nucypher.crypto.api import secure_random
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import Signature
from nucypher.crypto.splitters import signature_splitter


def test_message_kit_serialization_via_enrico(federated_alice):

    mock_label = b'this is a label'

    # Enrico
    enrico = Enrico.from_alice(federated_alice, label=mock_label)

    # Plaintext
    message = 'this is a message'
    plaintext_bytes = bytes(message, encoding='utf-8')

    # Create
    message_kit, signature = enrico.encrypt_message(plaintext=plaintext_bytes)

    # Serialize
    message_kit_bytes = message_kit.to_bytes()

    # Deserialize
    the_same_message_kit = UmbralMessageKit.from_bytes(message_kit_bytes)

    # Confirm
    assert message_kit_bytes == the_same_message_kit.to_bytes()
