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


import os
import pytest
from eth_tester.exceptions import TransactionFailed
from nucypher.crypto.umbral_adapter import Signer, SecretKey, generate_kfrags, encrypt, reencrypt


@pytest.fixture()
def deserializer(testerchain, deploy_contract):
    contract, _ = deploy_contract('UmbralDeserializerMock')
    return contract


@pytest.fixture(scope="module")
def fragments():
    delegating_privkey = SecretKey.random()
    delegating_pubkey = delegating_privkey.public_key()
    signing_privkey = SecretKey.random()
    signer = Signer(signing_privkey)
    priv_key_bob = SecretKey.random()
    pub_key_bob = priv_key_bob.public_key()
    kfrags = generate_kfrags(delegating_sk=delegating_privkey,
                             signer=signer,
                             receiving_pk=pub_key_bob,
                             threshold=2,
                             num_kfrags=4,
                             sign_delegating_key=False,
                             sign_receiving_key=False)

    capsule, _ciphertext = encrypt(delegating_pubkey, b'unused')
    cfrag = reencrypt(capsule, kfrags[0])
    return capsule, cfrag


def test_capsule(testerchain, deserializer, fragments):
    # Wrong number of bytes to deserialize capsule
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsule(os.urandom(97)).call()
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsule(os.urandom(99)).call()

    # Check random capsule bytes
    capsule_bytes = os.urandom(98)
    result = deserializer.functions.toCapsule(capsule_bytes).call()
    assert capsule_bytes == bytes().join(bytes(item) for item in result)

    # Check real capsule
    capsule, _cfrag = fragments
    capsule_bytes = bytes(capsule)
    result = deserializer.functions.toCapsule(capsule_bytes).call()
    assert b''.join(result) == capsule_bytes


def test_cfrag(testerchain, deserializer, fragments):
    # Wrong number of bytes to deserialize cfrag
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsuleFrag(os.urandom(358)).call()

    # Check random cfrag bytes
    cfrag_bytes = os.urandom(131)
    proof_bytes = os.urandom(228)
    full_cfrag_bytes = cfrag_bytes + proof_bytes
    result = deserializer.functions.toCapsuleFrag(full_cfrag_bytes).call()
    assert cfrag_bytes == bytes().join(result)
    result = deserializer.functions.toCorrectnessProofFromCapsuleFrag(full_cfrag_bytes).call()
    assert proof_bytes == bytes().join(result)

    # Check real cfrag
    _capsule, cfrag = fragments
    cfrag_bytes = bytes(cfrag)
    result_frag = deserializer.functions.toCapsuleFrag(cfrag_bytes).call()
    result_proof = deserializer.functions.toCorrectnessProofFromCapsuleFrag(cfrag_bytes).call()
    assert cfrag_bytes == b''.join(result_frag) + b''.join(result_proof)


# TODO: Missing test for precomputed_data
