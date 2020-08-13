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
from bytestring_splitter import VariableLengthBytestring
from eth_utils import to_canonical_address
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.blockchain.eth.constants import ETH_HASH_BYTE_LENGTH, LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from nucypher.crypto.signing import SignatureStamp
from nucypher.policy.collections import WorkOrder


def test_pre_task(mock_ursula_reencrypts, mocker, get_random_checksum_address):
    identity_evidence = os.urandom(LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY)
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))
    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=identity_evidence)

    evidence = mock_ursula_reencrypts(ursula)
    capsule = evidence.task.capsule
    capsule_bytes = capsule.to_bytes()

    signature = ursula_stamp(capsule_bytes)

    task = WorkOrder.PRETask(capsule=capsule, signature=signature)
    assert capsule == task.capsule
    assert signature == task.signature

    task_bytes = bytes(task)
    assert bytes(capsule) + bytes(signature) == task_bytes

    deserialized_task = WorkOrder.PRETask.from_bytes(task_bytes)
    assert capsule == deserialized_task.capsule
    assert signature == deserialized_task.signature

    # Attaching cfrags to the task
    cfrag = evidence.task.cfrag
    cfrag_bytes = bytes(VariableLengthBytestring(cfrag.to_bytes()))
    cfrag_signature = ursula_stamp(cfrag_bytes)

    task.attach_work_result(cfrag, cfrag_signature)
    assert capsule == task.capsule
    assert signature == task.signature
    assert cfrag == task.cfrag
    assert cfrag_signature == task.cfrag_signature

    task_bytes = bytes(task)
    assert bytes(capsule) + bytes(signature) + cfrag_bytes + bytes(cfrag_signature) == task_bytes

    deserialized_task = WorkOrder.PRETask.from_bytes(task_bytes)
    assert capsule == deserialized_task.capsule
    assert signature == deserialized_task.signature
    assert bytes(cfrag) == bytes(deserialized_task.cfrag)  # We compare bytes as there's no CapsuleFrag.__eq__
    assert cfrag_signature == deserialized_task.cfrag_signature

    # Task specification
    alice_address = to_canonical_address(get_random_checksum_address())
    blockhash = os.urandom(ETH_HASH_BYTE_LENGTH)

    specification = task.get_specification(bytes(ursula_stamp), alice_address, blockhash, identity_evidence)

    expected_specification = bytes(capsule) + bytes(ursula_stamp) + identity_evidence + alice_address + blockhash
    assert expected_specification == specification

    with pytest.raises(ValueError, match=f"blockhash must be of length {ETH_HASH_BYTE_LENGTH}"):
        task.get_specification(bytes(ursula_stamp), alice_address, os.urandom(42), identity_evidence)
