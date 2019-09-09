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
from constant_sorrow.constants import DO_NOT_SIGN
from umbral.keys import UmbralPrivateKey

from nucypher.crypto.api import encrypt_and_sign
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import Signer, SignatureStamp


@pytest.fixture(scope='module')
def stamp():
    signing_key = UmbralPrivateKey.gen_key()
    signer = Signer(signing_key)
    stamp = SignatureStamp(signing_key.pubkey, signer)
    return stamp


def test_message_kit_serialization(stamp):
    privkey = UmbralPrivateKey.gen_key()
    message = b"test"
    message_kit, _ = encrypt_and_sign(recipient_pubkey_enc=privkey.pubkey,
                                      plaintext=message,
                                      stamp=stamp,
                                      sign_plaintext=True)

    serialized_kit = message_kit.to_bytes()
    assert bytes(message_kit) == serialized_kit
    deserialized_kit = UmbralMessageKit.from_bytes(serialized_kit)
    assert message_kit == deserialized_kit
    b64_kit = message_kit.to_base64()
    deserialized_kit = UmbralMessageKit.from_base64(b64_kit)
    assert message_kit == deserialized_kit

    message_kit, _ = encrypt_and_sign(recipient_pubkey_enc=privkey.pubkey,
                                      plaintext=message,
                                      stamp=DO_NOT_SIGN)

    with pytest.raises(ValueError):
        _serialized_kit = message_kit.to_bytes()
    serialized_kit = message_kit.to_bytes(include_sender_verifying_key=False)
    assert bytes(message_kit) == serialized_kit
    deserialized_kit = UmbralMessageKit.from_bytes(serialized_kit)
    assert message_kit == deserialized_kit
    b64_kit = message_kit.to_base64()
    deserialized_kit = UmbralMessageKit.from_base64(b64_kit)
    assert message_kit == deserialized_kit
    