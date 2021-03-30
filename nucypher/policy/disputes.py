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


from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from typing import Tuple

from nucypher.crypto.utils import get_coordinates_as_bytes, get_signature_recovery_value
from nucypher.policy.orders import WorkOrder
from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPublicKey


# TODO: Change name to EvaluationEvidence
class IndisputableEvidence:

    def __init__(self,
                 task: WorkOrder.PRETask,
                 work_order: WorkOrder,
                 delegating_pubkey: UmbralPublicKey = None,
                 receiving_pubkey: UmbralPublicKey = None,
                 verifying_pubkey: UmbralPublicKey = None):

        self.task = task
        self.ursula_pubkey = work_order.ursula.stamp.as_umbral_pubkey()
        self.ursula_identity_evidence = work_order.ursula.decentralized_identity_evidence
        self.bob_verifying_key = work_order.bob.stamp.as_umbral_pubkey()
        self.encrypted_kfrag = work_order.encrypted_kfrag

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

        specification = self.task.get_specification(ursula_stamp=self.ursula_pubkey,
                                                    encrypted_kfrag=self.encrypted_kfrag,
                                                    identity_evidence=self.ursula_identity_evidence)

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

            # TODO: How is this supposed to be used? Revisit with updated umbral API in mind.
            # FIXME: This is not alice's address. It needs to be alice's verifying key as an ethereum address...?
            # self.alice_address,

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
                self.precompute_values())
