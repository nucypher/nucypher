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
from bytestring_splitter import VariableLengthBytestring
from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.crypto.signing import SignatureStamp
from nucypher.policy.collections import WorkOrder


def test_pre_task_serialization(mock_ursula_reencrypts, mocker):
    ursula_privkey = UmbralPrivateKey.gen_key()
    ursula_stamp = SignatureStamp(verifying_key=ursula_privkey.pubkey,
                                  signer=Signer(ursula_privkey))
    ursula = mocker.Mock(stamp=ursula_stamp, decentralized_identity_evidence=b'')

    evidence = mock_ursula_reencrypts(ursula)
    capsule = evidence.task.capsule
    capsule_bytes = capsule.to_bytes()

    signature = ursula_stamp(capsule_bytes)  # FIXME

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
