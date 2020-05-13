import pytest
from umbral import pre
from umbral.signing import Signer
from umbral.config import default_params
from umbral.keys import UmbralPrivateKey

from nucypher.policy.collections import TreasureMap
from nucypher.crypto.kits import UmbralMessageKit
from tests.performance_mocks import NotAPrivateKey, NotAPublicKey
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

