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
from typing import Optional, Tuple, Callable, Sequence

import maya
from bytestring_splitter import BytestringKwargifier
from bytestring_splitter import (
    BytestringSplitter,
    BytestringSplittingError,
    VariableLengthBytestring
)
from constant_sorrow.constants import CFRAG_NOT_RETAINED, NO_DECRYPTION_PERFORMED, NOT_SIGNED
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_utils import to_canonical_address, to_checksum_address
from umbral.config import default_params
from umbral.keys import UmbralPublicKey
from umbral.pre import Capsule

from nucypher.blockchain.eth.constants import ETH_ADDRESS_BYTE_LENGTH, ETH_HASH_BYTE_LENGTH
from nucypher.characters.lawful import Bob, Character
from nucypher.crypto.api import encrypt_and_sign, keccak_digest
from nucypher.crypto.api import verify_eip_191
from nucypher.crypto.constants import HRAC_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower
from nucypher.crypto.signing import InvalidSignature, Signature, signature_splitter, SignatureStamp
from nucypher.crypto.splitters import capsule_splitter, key_splitter
from nucypher.crypto.splitters import cfrag_splitter
from nucypher.crypto.utils import (
    get_coordinates_as_bytes,
    get_signature_recovery_value
    canonical_address_from_umbral_key,
)
from nucypher.network.middleware import RestMiddleware


class TreasureMap:

    version = bytes.fromhex('42')  # TODO: Versioning

    class NowhereToBeFound(RestMiddleware.NotFound):
        """
        Called when no known nodes have it.
        """

    class IsDisorienting(Bob.NotEnoughNodes):
        """
        Called when an oriented TreasureMap lists fewer than m destinations, which
        leaves Bob disoriented.
        """

    ursula_and_kfrag_splitter = BytestringSplitter((to_checksum_address, ETH_ADDRESS_BYTE_LENGTH),
                                                   (UmbralMessageKit, VariableLengthBytestring))

    from nucypher.crypto.signing import \
        InvalidSignature  # Raised when the public signature (typically intended for Ursula) is not valid.

    def __init__(self,
                 m: int = None,
                 destinations=None,
                 message_kit: UmbralMessageKit = None,
                 public_signature: Signature = None,
                 hrac: Optional[bytes] = None,
                 version: bytes = None) -> None:

        if version is not None:
            self.version = version

        if m is not None:
            if m > 255:
                raise ValueError("Largest allowed value for m is 255.")
            self._m = m

            self._destinations = destinations or {}
        else:
            self._m = NO_DECRYPTION_PERFORMED
            self._destinations = NO_DECRYPTION_PERFORMED

        self._id = None

        self.message_kit = message_kit
        self._public_signature = public_signature
        self._hrac = hrac
        self._payload = None

        if message_kit is not None:
            self.message_kit = message_kit
            self._set_id()
        else:
            self.message_kit = None

    @classmethod
    def splitter(cls):
        return BytestringKwargifier(cls,
                                    version=(bytes, 1),
                                    public_signature=Signature,
                                    hrac=(bytes, HRAC_LENGTH),
                                    message_kit=(UmbralMessageKit, VariableLengthBytestring))

    def prepare_for_publication(self,
                                bob_encrypting_key,
                                bob_verifying_key,
                                alice_stamp,
                                label: bytes):

        plaintext = self._m.to_bytes(1, "big") + self.nodes_as_bytes()

        self.message_kit, _signature_for_bob = encrypt_and_sign(bob_encrypting_key,
                                                                plaintext=plaintext,
                                                                signer=alice_stamp)
        """
        Here's our "hashed resource access code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.

        This way, Bob can generate it and use it to find the TreasureMap.
        """
        self._hrac = keccak_digest(bytes(alice_stamp) + bytes(bob_verifying_key) + label)[:HRAC_LENGTH]
        self._public_signature = alice_stamp(bytes(alice_stamp) + self._hrac)
        self._set_payload()
        self._set_id()

    def _set_id(self):
        self._id = keccak_digest(bytes(self._verifying_key) + bytes(self._hrac)).hex()

    def _set_payload(self) -> None:
        self._payload = self.version \
                        + self._public_signature \
                        + self._hrac \
                        + bytes(VariableLengthBytestring(self.message_kit.to_bytes()))

    def __bytes__(self):
        if self._payload is None:
            self._set_payload()
        return self._payload

    @property
    def _verifying_key(self):
        return self.message_kit.sender_verifying_key

    @property
    def m(self):
        if self._m == NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._m

    @property
    def destinations(self):
        if self._destinations == NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._destinations

    def nodes_as_bytes(self):
        if self.destinations == NO_DECRYPTION_PERFORMED:
            return NO_DECRYPTION_PERFORMED
        else:
            nodes_as_bytes = b""
            for ursula_address, encrypted_kfrag in self.destinations.items():
                node_id = to_canonical_address(ursula_address)
                kfrag = bytes(VariableLengthBytestring(encrypted_kfrag.to_bytes()))
                nodes_as_bytes += (node_id + kfrag)
            return nodes_as_bytes

    def add_kfrag(self, ursula, kfrag, signer_stamp: SignatureStamp):
        if self.destinations == NO_DECRYPTION_PERFORMED:
            raise TypeError("This TreasureMap is encrypted.  You can't add another node without decrypting it.")
        encrypted_kfrag = encrypt_and_sign(recipient_pubkey_enc=ursula.public_keys(DecryptingPower),
                                           plaintext=bytes(kfrag),
                                           signer=signer_stamp)[0]
        self.destinations[ursula.checksum_address] = encrypted_kfrag

    def public_id(self) -> str:
        """
        We need an ID that Bob can glean from knowledge he already has *and* which Ursula can verify came from Alice.
        Ursula will refuse to propagate this if it she can't prove the payload is signed by Alice's public key,
        which is included in it,
        """
        return self._id

    @classmethod
    def from_bytes(cls, bytes_representation, verify=True):
        splitter = cls.splitter()
        treasure_map = splitter(bytes_representation)
        if verify:
            treasure_map.public_verify()
        return treasure_map

    def public_verify(self):
        message = bytes(self._verifying_key) + self._hrac
        verified = self._public_signature.verify(message, self._verifying_key)

        if verified:
            return True
        else:
            raise self.InvalidSignature("This TreasureMap is not properly publicly signed by Alice.")

    def orient(self, compass: Callable):
        """
        When Bob receives the TreasureMap, he'll pass a compass (a callable which can verify and decrypt the
        payload message kit).
        """
        try:
            map_in_the_clear = compass(message_kit=self.message_kit)
        except Character.InvalidSignature:
            raise self.InvalidSignature("This TreasureMap does not contain the correct signature from Alice to Bob.")
        else:
            self._m = map_in_the_clear[0]
            try:
                ursula_and_kfrags = self.ursula_and_kfrag_splitter.repeat(map_in_the_clear[1:])
                self._destinations = {u: k for u, k in ursula_and_kfrags}
            except BytestringSplittingError:
                self._destinations = {}
            self.check_for_sufficient_destinations()

    def check_for_sufficient_destinations(self):
        if len(self._destinations) < self._m or self._m == 0:
            raise self.IsDisorienting(
                f"TreasureMap lists only {len(self._destinations)} destination, "
                f"but requires interaction with {self._m} nodes.")

    def __eq__(self, other):
        try:
            return self.public_id() == other.public_id()
        except AttributeError:
            raise TypeError(f"Can't compare {other} to a TreasureMap (it needs to implement public_id() )")

    def __iter__(self):
        return iter(self.destinations.items())

    def __len__(self):
        return len(self.destinations)

    def __repr__(self):
        return f"{self.__class__.__name__}:{self.public_id()[:6]}"


class SignedTreasureMap(TreasureMap):

    def __init__(self, blockchain_signature=NOT_SIGNED, *args, **kwargs):
        self._blockchain_signature = blockchain_signature
        super().__init__(*args, **kwargs)

    @classmethod
    def splitter(cls):
        return BytestringKwargifier(cls,
                                    version=(bytes, 1),
                                    public_signature=Signature,
                                    hrac=(bytes, HRAC_LENGTH),
                                    message_kit=(UmbralMessageKit, VariableLengthBytestring),
                                    blockchain_signature=65)

    def include_blockchain_signature(self, blockchain_signer):
        self._blockchain_signature = blockchain_signer(super().__bytes__())

    def verify_blockchain_signature(self, checksum_address):
        self._set_payload()
        return verify_eip_191(message=self._payload,
                              signature=self._blockchain_signature,
                              address=checksum_address)

    def __bytes__(self):
        if self._blockchain_signature is NOT_SIGNED:
            raise self.InvalidSignature(
                "Can't cast a SignedTreasureMap to bytes until it has a blockchain signature "
                "(otherwise, is it really a 'SignedTreasureMap'?")
        return super().__bytes__() + self._blockchain_signature


class WorkOrder:
    class PRETask:

        input_splitter = capsule_splitter + signature_splitter  # splitter for task without cfrag and signature
        output_splitter = cfrag_splitter + signature_splitter

        def __init__(self, capsule, signature, cfrag=None, cfrag_signature=None):
            self.capsule = capsule
            self.signature = signature
            self.cfrag = cfrag  # TODO: we need to store them in case of Ursula misbehavior
            self.cfrag_signature = cfrag_signature

        def get_specification(self,
                              ursula_stamp: SignatureStamp,
                              ursula_identity_evidence: Optional[bytes] = b''
                              ) -> bytes:

            ursula_pubkey = bytes(ursula_stamp)
            ursula_identity_evidence = bytes(ursula_identity_evidence)

            # FIXME: Include full specification
            expected_lengths = (
                (ursula_pubkey, 'ursula_pubkey', UmbralPublicKey.expected_bytes_length()),
                # (blockhash, 'blockhash', ETH_HASH_BYTE_LENGTH),
                # NOTE: ursula_identity_evidence has a default value of b'' for federated mode.
            )

            for parameter, name, expected_length in expected_lengths:
                if len(parameter) != expected_length:
                    raise ValueError(f"{name} must be of length {expected_length}, but it's {len(parameter)}")

            task_specification = (
                bytes(self.capsule),
                ursula_pubkey,
                ursula_identity_evidence
            )
            return b''.join(task_specification)

        def __bytes__(self):
            data = bytes(self.capsule) + bytes(self.signature)
            if self.cfrag and self.cfrag_signature:
                data += VariableLengthBytestring(self.cfrag) + bytes(self.cfrag_signature)
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

    HEADER = b"wo:"

    # receipt signature
    # publisher verifying key
    # authorizer verifying key
    # bob stamp
    # HRAC
    # encrypted kfrag
    # tasks
    payload_splitter = BytestringSplitter(Signature) \
                       + key_splitter \
                       + key_splitter \
                       + key_splitter \
                       + BytestringSplitter((bytes, HRAC_LENGTH)) \
                       + BytestringSplitter((bytes, VariableLengthBytestring))

    def __init__(self,
                 bob: Bob,
                 hrac: bytes,
                 encrypted_kfrag: bytes,
                 authorizer_verifying_key: bytes,
                 publisher_verifying_key: bytes,
                 tasks: dict,
                 receipt_signature: Signature,
                 ursula: Optional['Ursula'] = None
                 ):

        self.bob = bob
        self.hrac = hrac
        self.ursula = ursula
        self.encrypted_kfrag = encrypted_kfrag
        self.publisher_verifying_key = publisher_verifying_key
        self.authorizer_verifying_key = authorizer_verifying_key
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
    def _make_receipt(tasks, bob, ursula) -> bytes:
        # TODO: What's the goal of the receipt? Should it include only the capsules?
        # FIXME: Include encrypted KFrag in the receipt
        capsules = b''.join(map(bytes, tasks.keys()))
        receipt_bytes = WorkOrder.HEADER + bytes(ursula.stamp) + capsules
        receipt = bob.stamp(receipt_bytes)
        return receipt

    @classmethod
    def construct_by_bob(cls,
                         label: bytes,
                         publisher_verifying_key: UmbralPublicKey,
                         authorizer_verifying_key: UmbralPublicKey,
                         capsules: Sequence,
                         ursula: 'Ursula',
                         bob: Bob,
                         encrypted_kfrag: bytes):

        # In the event of a challenge, decentralized_identity_evidence
        # can be used to prove that ursula was/is a valid worker at the
        # time of the re-encryption request.
        ursula.mature()
        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        # FIXME: Include encrypted_kfrag in task specification
        tasks = OrderedDict()
        for capsule in capsules:
            task = cls.PRETask(capsule, signature=None)
            specification = task.get_specification(ursula_stamp=ursula.stamp,
                                                   ursula_identity_evidence=ursula_identity_evidence)
            task.signature = bob.stamp(specification)
            tasks[capsule] = task

        receipt = cls._make_receipt(tasks=tasks, bob=bob, ursula=ursula)
        hrac = bob.construct_policy_hrac(verifying_key=publisher_verifying_key, label=label)
        return cls(bob=bob,
                   ursula=ursula,
                   hrac=hrac,
                   tasks=tasks,
                   receipt_signature=receipt,
                   encrypted_kfrag=encrypted_kfrag,
                   publisher_verifying_key=publisher_verifying_key,
                   authorizer_verifying_key=authorizer_verifying_key)

    def payload(self) -> bytes:
        """
        Creates a serialized WorkOrder. Called by Bob requesting reencryption tasks

        # receipt signature
        # publisher verifying key
        # authorizer verifying key
        # bob stamp
        # HRAC
        # encrypted kfrag
        # tasks

        """
        tasks_bytes = b''.join(bytes(item) for item in self.tasks.values())
        return bytes(self.receipt_signature)                        \
            + bytes(self.publisher_verifying_key)                   \
            + bytes(self.authorizer_verifying_key)                  \
            + bytes(self.bob.stamp)                                 \
            + bytes(self.hrac)                                      \
            + bytes(VariableLengthBytestring(self.encrypted_kfrag)) \
            + tasks_bytes

    @classmethod
    def from_rest_payload(cls, rest_payload: bytes, ursula: 'Ursula'):
        result = cls.payload_splitter(rest_payload, return_remainder=True)
        signature, publisher_verifying, authorizer_verifying, bob_verifying, hrac, kfrag, remainder = result
        tasks = {capsule: cls.PRETask(capsule, sig) for capsule, sig in cls.PRETask.input_splitter.repeat(remainder)}

        # FIXME: Include kfrag in checks
        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        for task in tasks.values():
            # Each task signature has to match the original specification
            specification = task.get_specification(ursula_stamp=ursula.stamp,
                                                   ursula_identity_evidence=ursula_identity_evidence)

            if not task.signature.verify(specification, bob_verifying):
                raise InvalidSignature()

        # Check receipt
        capsules = b''.join(map(bytes, tasks.keys()))
        receipt_bytes = cls.HEADER + bytes(ursula.stamp) + capsules
        if not signature.verify(receipt_bytes, bob_verifying):
            raise InvalidSignature()

        bob = Bob.from_public_keys(verifying_key=bob_verifying)
        return cls(bob=bob,
                   hrac=hrac,
                   ursula=ursula,
                   tasks=tasks,
                   encrypted_kfrag=kfrag,
                   publisher_verifying_key=publisher_verifying,
                   authorizer_verifying_key=authorizer_verifying,
                   receipt_signature=signature)

    def complete(self, cfrags_and_signatures):
        good_cfrags = []
        if not len(self) == len(cfrags_and_signatures):
            raise ValueError("Ursula gave back the wrong number of cfrags. She's up to something.")

        ursula_verifying_key = self.ursula.stamp.as_umbral_pubkey()

        for task, (cfrag, cfrag_signature) in zip(self.tasks.values(), cfrags_and_signatures):
            # Validate re-encryption metadata
            metadata_input = bytes(task.signature)
            metadata_as_signature = Signature.from_bytes(cfrag.proof.metadata)
            if not metadata_as_signature.verify(metadata_input, ursula_verifying_key):
                raise InvalidSignature(f"Invalid metadata for {cfrag}.")
                # TODO: Instead of raising, we should do something (#957)

            # Validate re-encryption signatures
            if cfrag_signature.verify(bytes(cfrag), ursula_verifying_key):
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
    revocation_splitter = BytestringSplitter((bytes, 7), (bytes, 32), Signature)

    def __init__(self,
                 encrypted_kfrag: bytes,
                 signer: 'SignatureStamp' = None,
                 signature: Signature = None
                 ):

        self.prefix = b'REVOKE-'
        self.encrypted_kfrag = encrypted_kfrag

        if not (bool(signer) ^ bool(signature)):
            raise ValueError("Either pass a signer or a signature; not both.")
        elif signer:
            self.signature = signer(self.prefix + bytes(self.encrypted_kfrag))
        elif signature:
            self.signature = signature

    def __bytes__(self):
        return self.prefix + self.encrypted_kfrag + bytes(self.signature)

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @classmethod
    def from_bytes(cls, revocation_bytes):
        _, arrangement_id, signature = cls.revocation_splitter(revocation_bytes)
        return cls(arrangement_id, signature=signature)

    def verify_signature(self, alice_pubkey: 'UmbralPublicKey') -> bool:
        """
        Verifies the revocation was from the provided pubkey.
        """
        if not self.signature.verify(self.prefix + self.encrypted_kfrag, alice_pubkey):
            raise InvalidSignature("Revocation has an invalid signature: {}".format(self.signature))
        return True


# TODO: Change name to EvaluationEvidence
class IndisputableEvidence:

    def __init__(self,
                 task: 'WorkOrder.Task',
                 work_order: 'WorkOrder',
                 delegating_pubkey: UmbralPublicKey = None,
                 receiving_pubkey: UmbralPublicKey = None,
                 verifying_pubkey: UmbralPublicKey = None,
                 ) -> None:

        self.task = task
        self.ursula_pubkey = work_order.ursula.stamp.as_umbral_pubkey()
        self.ursula_identity_evidence = work_order.ursula.decentralized_identity_evidence
        self.bob_verifying_key = work_order.bob.stamp.as_umbral_pubkey()
        self.blockhash = work_order.blockhash
        self.alice_address = work_order.alice_address

        keys = self.task.capsule.get_correctness_keys()
        key_types = ("delegating", "receiving", "verifying")
        if all(keys[key_type] for key_type in key_types):
            self.delegating_pubkey = keys["delegating"]
            self.receiving_pubkey = keys["receiving"]
            self.verifying_pubkey = keys["verifying"]
        elif all((delegating_pubkey, receiving_pubkey, verifying_pubkey)):
            self.delegating_pubkey = delegating_pubkey
            self.receiving_pubkey = receiving_pubkey
            self.verifying_pubkey = verifying_pubkey
        else:
            raise ValueError("All correctness keys are required to compute evidence.  "
                             "Either pass them as arguments or in the capsule.")

        # TODO: check that the metadata is correct.

    def get_proof_challenge_scalar(self) -> CurveBN:
        capsule = self.task.capsule
        cfrag = self.task.cfrag

        umbral_params = default_params()
        e, v, _ = capsule.components()

        e1 = cfrag.point_e1
        v1 = cfrag.point_v1
        e2 = cfrag.proof.point_e2
        v2 = cfrag.proof.point_v2
        u = umbral_params.u
        u1 = cfrag.proof.point_kfrag_commitment
        u2 = cfrag.proof.point_kfrag_pok
        metadata = cfrag.proof.metadata

        from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak

        hash_input = (e, e1, e2, v, v1, v2, u, u1, u2, metadata)

        h = hash_to_curvebn(*hash_input, params=umbral_params, hash_class=ExtendedKeccak)
        return h

    def precompute_values(self) -> bytes:
        capsule = self.task.capsule
        cfrag = self.task.cfrag

        umbral_params = default_params()
        e, v, _ = capsule.components()

        e1 = cfrag.point_e1
        v1 = cfrag.point_v1
        e2 = cfrag.proof.point_e2
        v2 = cfrag.proof.point_v2
        u = umbral_params.u
        u1 = cfrag.proof.point_kfrag_commitment
        u2 = cfrag.proof.point_kfrag_pok
        metadata = cfrag.proof.metadata

        h = self.get_proof_challenge_scalar()

        e1h = h * e1
        v1h = h * v1
        u1h = h * u1

        z = cfrag.proof.bn_sig
        ez = z * e
        vz = z * v
        uz = z * u

        only_y_coord = dict(x_coord=False, y_coord=True)
        # E points
        e_y = get_coordinates_as_bytes(e, **only_y_coord)
        ez_xy = get_coordinates_as_bytes(ez)
        e1_y = get_coordinates_as_bytes(e1, **only_y_coord)
        e1h_xy = get_coordinates_as_bytes(e1h)
        e2_y = get_coordinates_as_bytes(e2, **only_y_coord)
        # V points
        v_y = get_coordinates_as_bytes(v, **only_y_coord)
        vz_xy = get_coordinates_as_bytes(vz)
        v1_y = get_coordinates_as_bytes(v1, **only_y_coord)
        v1h_xy = get_coordinates_as_bytes(v1h)
        v2_y = get_coordinates_as_bytes(v2, **only_y_coord)
        # U points
        uz_xy = get_coordinates_as_bytes(uz)
        u1_y = get_coordinates_as_bytes(u1, **only_y_coord)
        u1h_xy = get_coordinates_as_bytes(u1h)
        u2_y = get_coordinates_as_bytes(u2, **only_y_coord)

        # Get hashed KFrag validity message
        hash_function = hashes.Hash(hashes.SHA256(), backend=backend)

        kfrag_id = cfrag.kfrag_id
        precursor = cfrag.point_precursor
        delegating_pubkey = self.delegating_pubkey
        receiving_pubkey = self.receiving_pubkey

        validity_input = (kfrag_id, delegating_pubkey, receiving_pubkey, u1, precursor)
        kfrag_validity_message = bytes().join(bytes(item) for item in validity_input)
        hash_function.update(kfrag_validity_message)
        hashed_kfrag_validity_message = hash_function.finalize()

        # Get KFrag signature's v value
        kfrag_signature_v = get_signature_recovery_value(message=hashed_kfrag_validity_message,
                                                         signature=cfrag.proof.kfrag_signature,
                                                         public_key=self.verifying_pubkey,
                                                         is_prehashed=True)

        cfrag_signature_v = get_signature_recovery_value(message=bytes(cfrag),
                                                         signature=self.task.cfrag_signature,
                                                         public_key=self.ursula_pubkey)

        metadata_signature_v = get_signature_recovery_value(message=self.task.signature,
                                                            signature=metadata,
                                                            public_key=self.ursula_pubkey)

        specification = self.task.get_specification(ursula_pubkey=self.ursula_pubkey,
                                                    alice_address=self.alice_address,
                                                    blockhash=self.blockhash,
                                                    ursula_identity_evidence=self.ursula_identity_evidence)

        specification_signature_v = get_signature_recovery_value(message=specification,
                                                                 signature=self.task.signature,
                                                                 public_key=self.bob_verifying_key)

        ursula_pubkey_prefix_byte = bytes(self.ursula_pubkey)[0:1]

        # Bundle everything together
        pieces = (
            e_y, ez_xy, e1_y, e1h_xy, e2_y,
            v_y, vz_xy, v1_y, v1h_xy, v2_y,
            uz_xy, u1_y, u1h_xy, u2_y,
            hashed_kfrag_validity_message,

            # TODO: Revisit this with updated umbral API.
            # FIXME: This is not alice's address.
            # It needs to be alice's verifying key as an ethereum address.
            self.alice_address,

            # The following single-byte values are interpreted as a single bytes5 variable by the Solidity contract
            kfrag_signature_v,
            cfrag_signature_v,
            metadata_signature_v,
            specification_signature_v,
            ursula_pubkey_prefix_byte,
        )
        return b''.join(pieces)

    def evaluation_arguments(self) -> Tuple:
        return (bytes(self.task.capsule),
                bytes(self.task.cfrag),
                bytes(self.task.cfrag_signature),
                bytes(self.task.signature),
                get_coordinates_as_bytes(self.bob_verifying_key),
                get_coordinates_as_bytes(self.ursula_pubkey),
                bytes(self.ursula_identity_evidence),
                self.precompute_values()
                )
