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


from collections import OrderedDict
from typing import Optional, Dict, Sequence, Union

import maya
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import CFRAG_NOT_RETAINED
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_canonical_address, to_checksum_address

from nucypher.crypto.kits import PolicyMessageKit
from nucypher.crypto.signing import SignatureStamp, InvalidSignature
from nucypher.crypto.splitters import (
    key_splitter,
    capsule_splitter,
    cfrag_splitter,
    signature_splitter,
    hrac_splitter,
    kfrag_splitter
)
from nucypher.crypto.umbral_adapter import (
    Capsule,
    CapsuleFrag,
    PublicKey,
    Signature
)
from nucypher.policy.maps import AuthorizedKeyFrag


class WorkOrder:

    RECEIPT_HEADER = b"wo:"

    # receipt signature
    # alice verifying key
    # relayer verifying key
    # bob stamp
    # HRAC
    # encrypted kfrag
    # tasks
    payload_splitter = signature_splitter \
        + key_splitter                    \
        + key_splitter                    \
        + key_splitter                    \
        + hrac_splitter                   \
        + BytestringSplitter((bytes, VariableLengthBytestring))

    class PRETask:

        input_splitter = capsule_splitter + signature_splitter  # splitter for task without cfrag and signature
        output_splitter = cfrag_splitter + signature_splitter

        def __init__(self,
                     capsule: Capsule,
                     signature: Signature,
                     cfrag: Optional[CapsuleFrag] = None,
                     cfrag_signature: Optional[Signature] = None):

            self.capsule = capsule
            self.signature = signature
            self.cfrag = cfrag  # TODO: Store cfrags in case of Ursula misbehavior?
            self.cfrag_signature = cfrag_signature

        def get_specification(self,
                              ursula_stamp: SignatureStamp,
                              encrypted_kfrag: Union[PolicyMessageKit, bytes],
                              identity_evidence: Optional[bytes] = b''
                              ) -> bytes:

            stamp = bytes(ursula_stamp)
            encrypted_kfrag = bytes(encrypted_kfrag)
            identity_evidence = bytes(identity_evidence)

            expected_lengths = (
                (stamp, 'ursula_stamp', PublicKey.serialized_size()),
                (encrypted_kfrag, 'encrypted_kfrag', AuthorizedKeyFrag.ENCRYPTED_SIZE)
                # NOTE: ursula_identity_evidence has a default value of b'' for federated mode.
            )

            for parameter, name, expected_length in expected_lengths:
                if len(parameter) != expected_length:
                    raise ValueError(f"{name} must be of length {expected_length}, but it's {len(parameter)}")

            task_specification = (
                bytes(self.capsule),
                stamp,
                identity_evidence
            )
            return b''.join(task_specification)

        def __bytes__(self):
            data = bytes(self.capsule) + bytes(self.signature)
            if self.cfrag and self.cfrag_signature:
                data += bytes(self.cfrag) + bytes(self.cfrag_signature)
            return data

        @classmethod
        def from_bytes(cls, data: bytes):
            capsule, signature, remainder = cls.input_splitter(data, return_remainder=True)
            if remainder:
                cfrag, reencryption_signature = cls.output_splitter(remainder)
                return cls(capsule=capsule, signature=signature, cfrag=cfrag, cfrag_signature=reencryption_signature)
            else:
                return cls(capsule=capsule, signature=signature)

        def attach_work_result(self, cfrag, cfrag_signature) -> None:
            self.cfrag = cfrag
            self.cfrag_signature = cfrag_signature

    def __init__(self,
                 bob: 'Bob',
                 hrac: bytes,
                 encrypted_kfrag: bytes,
                 alice_verifying_key: bytes,
                 publisher_verifying_key: bytes,
                 tasks: dict,
                 receipt_signature: Signature,
                 ursula: Optional['Ursula'] = None):

        self.bob = bob
        self.hrac = hrac
        self.ursula = ursula
        self.encrypted_kfrag = encrypted_kfrag
        self.publisher_verifying_key = publisher_verifying_key
        self.alice_verifying_key = alice_verifying_key
        self.tasks = tasks
        self.receipt_signature = receipt_signature  # not a blockchain receipt
        self.completed = False

    def __repr__(self):
        return "WorkOrder for hrac {hrac}: (capsules: {capsule_reprs}) for {node}".format(
            hrac=self.hrac,
            capsule_reprs=self.tasks.keys(),
            node=self.ursula)

    def __eq__(self, other):
        return self.receipt_signature == other.receipt_signature

    def __len__(self):
        return len(self.tasks)

    @staticmethod
    def make_receipt(tasks: Dict,
                     ursula: 'Ursula',
                     encrypted_kfrag: Union[PolicyMessageKit, bytes]
                     ) -> bytes:
        # TODO: What is the goal of the receipt and where can it be used?
        capsules = b''.join(map(bytes, tasks.keys()))
        receipt_bytes = WorkOrder.RECEIPT_HEADER + bytes(ursula.stamp) + bytes(encrypted_kfrag) + capsules
        return receipt_bytes

    @classmethod
    def construct_by_bob(cls,
                         label: bytes,
                         alice_verifying_key: PublicKey,
                         publisher_verifying_key: PublicKey,
                         capsules: Sequence,
                         ursula: 'Ursula',
                         bob: 'Bob',
                         encrypted_kfrag: bytes):

        # In the event of a challenge, decentralized_identity_evidence
        # can be used to prove that ursula was/is a valid worker at the
        # time of the re-encryption request.
        ursula.mature()
        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        tasks = OrderedDict()
        for capsule in capsules:
            task = cls.PRETask(capsule, signature=None)
            specification = task.get_specification(ursula_stamp=ursula.stamp,
                                                   encrypted_kfrag=encrypted_kfrag,
                                                   identity_evidence=ursula_identity_evidence)
            task.signature = bob.stamp(specification)
            tasks[capsule] = task

        receipt = cls.make_receipt(tasks=tasks, ursula=ursula, encrypted_kfrag=encrypted_kfrag)
        receipt_signature = bob.stamp(receipt)

        hrac = bob.construct_policy_hrac(publisher_verifying_key=publisher_verifying_key, label=label)
        return cls(bob=bob,
                   ursula=ursula,
                   hrac=hrac,
                   tasks=tasks,
                   receipt_signature=receipt_signature,
                   encrypted_kfrag=encrypted_kfrag,
                   publisher_verifying_key=publisher_verifying_key,
                   alice_verifying_key=alice_verifying_key)

    def payload(self) -> bytes:
        """
        Creates a serialized WorkOrder. Called by Bob requesting reencryption tasks

        # receipt signature
        # alice verifying key
        # relayer verifying key
        # bob stamp
        # HRAC
        # encrypted kfrag
        # tasks

        """
        tasks_bytes = b''.join(bytes(item) for item in self.tasks.values())
        result = bytes(self.receipt_signature)                                   \
                 + bytes(self.alice_verifying_key)                               \
                 + bytes(self.publisher_verifying_key)                             \
                 + bytes(self.bob.stamp)                                         \
                 + bytes(self.hrac)                                              \
                 + bytes(VariableLengthBytestring(self.encrypted_kfrag)) \
                 + tasks_bytes
        return result

    @classmethod
    def from_rest_payload(cls, rest_payload: bytes, ursula: 'Ursula'):

        # Deserialize
        result = cls.payload_splitter(rest_payload, return_remainder=True)
        signature, publisher_verifying, authorizer_verifying, bob_verifying, hrac, ekfrag, remainder = result
        tasks = {capsule: cls.PRETask(capsule, sig) for capsule, sig in cls.PRETask.input_splitter.repeat(remainder)}

        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        # Check Specification
        for task in tasks.values():
            # Each task signature has to match the original specification
            specification = task.get_specification(ursula_stamp=ursula.stamp,
                                                   encrypted_kfrag=ekfrag,
                                                   identity_evidence=ursula_identity_evidence)

            if not task.signature.verify(bob_verifying, specification):
                raise InvalidSignature()

        # Check receipt
        capsules = b''.join(map(bytes, tasks.keys()))
        receipt_bytes = cls.RECEIPT_HEADER + bytes(ursula.stamp) + bytes(ekfrag) + capsules
        if not signature.verify(message=receipt_bytes, verifying_key=bob_verifying):
            raise InvalidSignature()

        from nucypher.characters.lawful import Bob
        bob = Bob.from_public_keys(verifying_key=bob_verifying)
        return cls(bob=bob,
                   hrac=hrac,
                   ursula=ursula,
                   tasks=tasks,
                   encrypted_kfrag=ekfrag,
                   publisher_verifying_key=publisher_verifying,
                   alice_verifying_key=authorizer_verifying,
                   receipt_signature=signature)

    def complete(self, cfrags_and_signatures):
        good_cfrags = []
        if not len(self) == len(cfrags_and_signatures):
            raise ValueError("Ursula gave back the wrong number of cfrags. She's up to something.")

        ursula_verifying_key = self.ursula.stamp.as_umbral_pubkey()

        for task, (cfrag, cfrag_signature) in zip(self.tasks.values(), cfrags_and_signatures):

            # Validate re-encryption signatures
            if cfrag_signature.verify(ursula_verifying_key, bytes(cfrag)):
                good_cfrags.append(cfrag)
            else:
                raise InvalidSignature(f"{cfrag} is not properly signed by Ursula.")
                # TODO: Instead of raising, we should do something (#957)

        for task, (cfrag, cfrag_signature) in zip(self.tasks.values(), cfrags_and_signatures):
            task.attach_work_result(cfrag, cfrag_signature)

        self.completed = maya.now()
        return good_cfrags

    def sanitize(self):
        for task in self.tasks.values():
            task.cfrag = CFRAG_NOT_RETAINED


class WorkOrderHistory:

    def __init__(self) -> None:
        self.by_ursula = {}  # type: dict
        self._latest_replete = {}

    def __contains__(self, item):
        assert False

    def __getitem__(self, item):
        return self.by_ursula[item]

    def __setitem__(self, key, value):
        assert False

    def __len__(self):
        return sum(len(work_orders) for work_orders in self.by_ursula.values())

    @property
    def ursulas(self):
        return self.by_ursula.keys()

    def most_recent_replete(self, capsule):
        """
        Returns most recent WorkOrders for each Ursula which contain a complete task (with CFrag attached) for this Capsule.
        """
        return self._latest_replete[capsule]

    def save_work_order(self, work_order, as_replete=False):
        for task in work_order.tasks.values():
            if as_replete:
                work_orders_for_ursula = self._latest_replete.setdefault(task.capsule, {})
                work_orders_for_ursula[work_order.ursula.checksum_address] = work_order

            work_orders_for_ursula = self.by_ursula.setdefault(work_order.ursula.checksum_address, {})
            work_orders_for_ursula[task.capsule] = work_order

    def by_checksum_address(self, checksum_address):
        return self.by_ursula.setdefault(checksum_address, {})

    def by_capsule(self, capsule: Capsule):
        ursulas_by_capsules = {}  # type: dict
        for ursula, capsules in self.by_ursula.items():
            for saved_capsule, work_order in capsules.items():
                if saved_capsule == capsule:
                    ursulas_by_capsules[ursula] = work_order
        return ursulas_by_capsules


class Revocation:
    """
    Represents a string used by characters to perform a revocation on a specific
    Ursula. It's a bytestring made of the following format:
    REVOKE-<arrangement id to revoke><signature of the previous string>
    This is sent as a payload in a DELETE method to the /KFrag/ endpoint.
    """

    PREFIX = b'REVOKE-'
    revocation_splitter = BytestringSplitter(
        (bytes, len(PREFIX)),
        (bytes, 20),   # ursula canonical address
        (bytes, AuthorizedKeyFrag.ENCRYPTED_SIZE),  # encrypted kfrag payload (includes writ)
        signature_splitter
    )

    def __init__(self,
                 ursula_checksum_address: ChecksumAddress,  # TODO: Use staker address instead (what if the staker rebonds)?
                 encrypted_kfrag: bytes,
                 signer: 'SignatureStamp' = None,
                 signature: Signature = None):

        self.ursula_checksum_address = ursula_checksum_address
        self.encrypted_kfrag = encrypted_kfrag

        if not (bool(signer) ^ bool(signature)):
            raise ValueError("Either pass a signer or a signature; not both.")
        elif signer:
            self.signature = signer(self.payload)
        elif signature:
            self.signature = signature

    def __bytes__(self):
        return self.payload + bytes(self.signature)

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @property
    def payload(self):
        return self.PREFIX                                          \
               + to_canonical_address(self.ursula_checksum_address) \
               + bytes(self.encrypted_kfrag)                        \

    @classmethod
    def from_bytes(cls, revocation_bytes):
        prefix, ursula_canonical_address, ekfrag, signature = cls.revocation_splitter(revocation_bytes)
        ursula_checksum_address = to_checksum_address(ursula_canonical_address)
        return cls(ursula_checksum_address=ursula_checksum_address,
                   encrypted_kfrag=ekfrag,
                   signature=signature)

    def verify_signature(self, alice_verifying_key: 'PublicKey') -> bool:
        """
        Verifies the revocation was from the provided pubkey.
        """
        if not self.signature.verify(self.payload, alice_verifying_key):
            raise InvalidSignature(f"Revocation has an invalid signature: {self.signature}")
        return True
