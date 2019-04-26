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

from umbral import pre
from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.point import Point
from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak
from umbral.signing import Signature, Signer

from nucypher.policy.models import IndisputableEvidence

@pytest.fixture(scope='module')
def reencryption_validator(testerchain):
    contract, _ = testerchain.interface.deploy_contract('ReEncryptionValidatorMock')
    return contract


def fragments(metadata):
    delegating_privkey = UmbralPrivateKey.gen_key()
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    signing_privkey = UmbralPrivateKey.gen_key()
    signer = Signer(signing_privkey)
    priv_key_bob = UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()
    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=pub_key_bob,
                                 threshold=2,
                                 N=4,
                                 sign_delegating_key=False,
                                 sign_receiving_key=False)
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_privkey.get_pubkey())
    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)
    return capsule, cfrag


@pytest.mark.slow
def test_extended_keccak_to_bn(testerchain, reencryption_validator):
    test_data = os.urandom(40)
    h = hash_to_curvebn(test_data, params=default_params(), hash_class=ExtendedKeccak)
    assert int(h) == reencryption_validator.functions.extendedKeccakToBN(test_data).call()


@pytest.mark.slow
def test_ec_point_operations(testerchain, reencryption_validator):
    valid_point = Point.gen_rand()
    x, y = valid_point.to_affine()

    # Test is_on_curve
    assert reencryption_validator.functions.is_on_curve(x, y).call()

    bad_y = y - 1
    assert not reencryption_validator.functions.is_on_curve(x, bad_y).call()

    # Test check_compressed_point
    sign = 2 + (y % 2)
    assert reencryption_validator.functions.check_compressed_point(sign, x, y).call()

    bad_sign = 3 - (y % 2)
    assert not reencryption_validator.functions.check_compressed_point(bad_sign, x, y).call()

    # Test ecmulVerify
    P = valid_point
    scalar = CurveBN.gen_rand()
    Q = scalar * P
    qx, qy = Q.to_affine()

    assert reencryption_validator.functions.ecmulVerify(x, y, int(scalar), qx, qy).call()
    assert not reencryption_validator.functions.ecmulVerify(x, y, int(scalar), x, y).call()

    # Test eqAffineJacobian
    Q_affine = [qx, qy]
    Q_jacobian = [qx, qy, 1]
    assert reencryption_validator.functions.eqAffineJacobian(Q_affine, Q_jacobian).call()

    P_jacobian = [x, y, 1]
    assert not reencryption_validator.functions.eqAffineJacobian(Q_affine, P_jacobian).call()

    point_at_infinity = [x, y, 0]
    random_point = Point.gen_rand()
    assert not reencryption_validator.functions.eqAffineJacobian(random_point.to_affine(), point_at_infinity).call()

    # Test doubleJacobian
    doubleP = reencryption_validator.functions.doubleJacobian(P_jacobian).call()
    assert reencryption_validator.functions.eqAffineJacobian((P + P).to_affine(), doubleP).call()

    # Test addAffineJacobian
    scalar1 = CurveBN.gen_rand()
    scalar2 = CurveBN.gen_rand()
    R1 = scalar1 * P
    R2 = scalar2 * P

    assert R1 + R2 == (scalar1 + scalar2) * P
    R = reencryption_validator.functions.addAffineJacobian(R1.to_affine(), R2.to_affine()).call()
    assert reencryption_validator.functions.eqAffineJacobian((R1 + R2).to_affine(), R).call()

    P_plus_P = reencryption_validator.functions.addAffineJacobian(P.to_affine(), P.to_affine()).call()
    assert reencryption_validator.functions.eqAffineJacobian((P + P).to_affine(), P_plus_P).call()


# TODO: See https://github.com/nucypher/nucypher/issues/626#issuecomment-486186171
@pytest.mark.skip(reason="no way of testing library constants for the moment")
def test_umbral_constants(testerchain, reencryption_validator):
    umbral_params = default_params()
    u_xcoord, u_ycoord = umbral_params.u.to_affine()
    u_sign = 2 + (u_ycoord % 2)
    assert u_sign == reencryption_validator.functions.UMBRAL_PARAMETER_U_SIGN().call()
    assert u_xcoord == reencryption_validator.functions.UMBRAL_PARAMETER_U_XCOORD().call()
    assert u_ycoord == reencryption_validator.functions.UMBRAL_PARAMETER_U_YCOORD().call()


@pytest.mark.slow
def test_compute_proof_challenge_scalar(testerchain, reencryption_validator):
    metadata = os.urandom(33)
    capsule, cfrag = fragments(metadata)

    assert cfrag.verify_correctness(capsule)

    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()

    # Bob prepares supporting Evidence
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)

    proof_challenge_scalar = int(evidence.get_proof_challenge_scalar())
    computeProofChallengeScalar = reencryption_validator.functions.computeProofChallengeScalar
    assert proof_challenge_scalar == computeProofChallengeScalar(capsule_bytes, cfrag_bytes).call()


@pytest.mark.slow
def test_validate_cfrag(testerchain, reencryption_validator):
    ###############################
    # Test: Ursula produces correct proof:
    ###############################
    metadata = os.urandom(33)
    capsule, cfrag = fragments(metadata)

    assert cfrag.verify_correctness(capsule)

    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()

    # Bob prepares supporting Evidence
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)

    evidence_data = evidence.precompute_values()
    assert len(evidence_data) == 20 * 32 + 32 + 20 + 1

    # Challenge using good data
    args = (capsule_bytes, cfrag_bytes, evidence_data)
    assert reencryption_validator.functions.validateCFrag(*args).call()

    ###############################
    # Test: Ursula produces incorrect proof:
    ###############################
    cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)
    cfrag_bytes = cfrag.to_bytes()
    assert not cfrag.verify_correctness(capsule)

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()

    args = (capsule_bytes, cfrag_bytes, evidence_data)
    assert not reencryption_validator.functions.validateCFrag(*args).call()

    ###############################
    # Test: Bob produces wrong precomputed data
    ###############################

    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()
    assert cfrag.verify_correctness(capsule)

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()

    # Bob produces a random point and gets the bytes of coords x and y
    random_point_bytes = Point.gen_rand().to_bytes(is_compressed=False)[1:]
    # He uses this garbage instead of correct precomputation of z*E
    evidence_data = bytearray(evidence_data)
    evidence_data[32:32 + 64] = random_point_bytes
    evidence_data = bytes(evidence_data)

    args = (capsule_bytes, cfrag_bytes, evidence_data)

    # Evaluation must fail since Bob precomputed wrong values
    with pytest.raises(TransactionFailed):
        _ = reencryption_validator.functions.validateCFrag(*args).call()

