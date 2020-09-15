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

import maya
import pytest
import os
from umbral import pre
from umbral.signing import Signer
from nucypher.policy.collections import TreasureMap, SignedTreasureMap
from nucypher.policy.policies import Arrangement
from nucypher.crypto.kits import UmbralMessageKit
from tests.mock.performance_mocks import NotAPrivateKey, NotAPublicKey
from nucypher.crypto.signing import SignatureStamp


@pytest.fixture(scope='module')
def mock_treasuremap():

    class MockTreasureMap(TreasureMap):

        def public_verify(self):
            return True


    alicekey = NotAPrivateKey()
    alice_stamp = SignatureStamp(alicekey.public_key(), signer=Signer(alicekey))
    label = b'some-great-label'

    instance = MockTreasureMap(m=1)
    instance.prepare_for_publication(
        bob_encrypting_key=NotAPublicKey(),
        bob_verifying_key=NotAPublicKey(),
        alice_stamp=alice_stamp,
        label=label,
    )
    return instance


@pytest.fixture(scope='module')
def mock_messagekit():

    alice_priv_key = NotAPrivateKey()# UmbralPrivateKey.gen_key(params=default_params())
    alice_pub_key = alice_priv_key.get_pubkey()
    message = b'a message noone will hear'
    alice_stamp = SignatureStamp(alice_pub_key, signer=Signer(alice_priv_key))

    ciphertext, capsule = pre.encrypt(alice_pub_key, message)

    return UmbralMessageKit(
        ciphertext=ciphertext,
        capsule=capsule,
        sender_verifying_key=alice_stamp.as_umbral_pubkey(),
        signature=alice_priv_key.fake_signature)


@pytest.fixture(scope='module')
def mock_signed_treasuremap():

    class MockSignedTreasureMap(SignedTreasureMap):

        def public_verify(self):
            return True

        def include_blockchain_signature(self):
            self._blockchain_signature = os.urandom(65)

        def verify_blockchain_signature(self):
            self._set_payload()
            return True


    alicekey = NotAPrivateKey()
    alice_stamp = SignatureStamp(alicekey.public_key(), signer=Signer(alicekey))
    label = b'some-great-label'

    instance = MockSignedTreasureMap(m=1, blockchain_signature=os.urandom(65))
    instance.prepare_for_publication(
        bob_encrypting_key=NotAPublicKey(),
        bob_verifying_key=NotAPublicKey(),
        alice_stamp=alice_stamp,
        label=label,
    )
    return instance


@pytest.fixture(scope='module')
def mock_arrangement():

    alice_priv_key = NotAPrivateKey()
    alice_pub_key = alice_priv_key.get_pubkey()
    alice_stamp = SignatureStamp(alice_pub_key, signer=Signer(alice_priv_key))

    class MockAlice:

        def __init__(self, stamp):
            self.stamp = stamp

    arrangement = Arrangement(
        alice=MockAlice(alice_stamp),
        expiration=maya.now() + maya.timedelta(days=30)
    )
    return arrangement
