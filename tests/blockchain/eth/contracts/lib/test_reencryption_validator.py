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

from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.point import Point
from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak


@pytest.fixture(scope='module')
def reencryption_validator(testerchain):
    contract, _ = testerchain.interface.deploy_contract('ReEncryptionValidatorMock')
    return contract


@pytest.mark.slow
def test_extended_keccak_to_bn(testerchain, reencryption_validator):
    test_data = os.urandom(40)
    h = hash_to_curvebn(test_data, params=default_params(), hash_class=ExtendedKeccak)
    assert int(h) == reencryption_validator.functions.extendedKeccakToBN(test_data).call()


@pytest.mark.slow
def test_extended_keccak_to_bn(testerchain, reencryption_validator):
    test_data = os.urandom(40)
    h = hash_to_curvebn(test_data, params=default_params(), hash_class=ExtendedKeccak)
    assert int(h) == reencryption_validator.functions.extendedKeccakToBN(test_data).call()


@pytest.mark.slow
def test_ec_point_operations(testerchain, reencryption_validator):
    valid_point = Point.gen_rand()
    x, y = valid_point.to_affine()

    assert reencryption_validator.functions.is_on_curve(x, y).call()

    bad_y = y - 1
    assert not reencryption_validator.functions.is_on_curve(x, bad_y).call()

    sign = 2 + (y % 2)
    assert reencryption_validator.functions.check_compressed_point(sign, x, y).call()

    bad_sign = 3 - (y % 2)
    assert not reencryption_validator.functions.check_compressed_point(bad_sign, x, y).call()

    P = valid_point
    scalar = CurveBN.gen_rand()
    Q = scalar * P
    qx, qy = Q.to_affine()

    assert reencryption_validator.functions.ecmulVerify(x, y, int(scalar), qx, qy).call()
    assert not reencryption_validator.functions.ecmulVerify(x, y, int(scalar), x, y).call()
