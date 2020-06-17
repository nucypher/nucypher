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


def test_split_two_signatures():
    """
    We make two random Signatures and concat them.  Then split them and show that we got the proper result.
    """
    sig1 = Signature.from_bytes(secure_random(64))
    sig2 = Signature.from_bytes(secure_random(64))
    sigs_concatted = sig1 + sig2
    two_signature_splitter = BytestringSplitter(Signature, Signature)
    rebuilt_sig1, rebuilt_sig2 = two_signature_splitter(sigs_concatted)
    assert (sig1, sig2) == (rebuilt_sig1, rebuilt_sig2)


def test_split_signature_from_arbitrary_bytes():
    how_many_bytes = 10
    signature = Signature.from_bytes(secure_random(64))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, how_many_bytes))

    rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes)


def test_trying_to_extract_too_many_bytes_raises_typeerror():
    how_many_bytes = 10
    too_many_bytes = 11
    signature = Signature.from_bytes(secure_random(64))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, too_many_bytes))

    with pytest.raises(BytestringSplittingError):
        rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes, return_remainder=True)


def test_message_kit_serialization_via_enrico(enacted_federated_policy, federated_alice):

    # Enrico
    enrico = Enrico.from_alice(federated_alice, label=enacted_federated_policy.label)

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
