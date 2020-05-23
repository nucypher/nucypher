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
from decimal import Decimal, InvalidOperation

from nucypher.blockchain.eth.token import NU


def test_NU(token_economics):

    # Starting Small
    min_allowed_locked = NU(token_economics.minimum_allowed_locked, 'NuNit')
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked.to_nunits())

    min_NU_locked = int(str(token_economics.minimum_allowed_locked)[0:-18])
    expected = NU(min_NU_locked, 'NU')
    assert min_allowed_locked == expected

    # Starting Big
    min_allowed_locked = NU(min_NU_locked, 'NU')
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked)
    assert token_economics.minimum_allowed_locked == int(min_allowed_locked.to_nunits())
    assert str(min_allowed_locked) == '15000 NU'

    # Alternate construction
    assert NU(1, 'NU') == NU('1.0', 'NU') == NU(1.0, 'NU')

    # Arithmetic

    # NUs
    one_nu = NU(1, 'NU')
    zero_nu = NU(0, 'NU')
    one_hundred_nu = NU(100, 'NU')
    two_hundred_nu = NU(200, 'NU')
    three_hundred_nu = NU(300, 'NU')

    # Nits
    one_nu_wei = NU(1, 'NuNit')
    three_nu_wei = NU(3, 'NuNit')
    assert three_nu_wei.to_tokens() == Decimal('3E-18')
    assert one_nu_wei.to_tokens() == Decimal('1E-18')

    # Base Operations
    assert one_hundred_nu < two_hundred_nu < three_hundred_nu
    assert one_hundred_nu <= two_hundred_nu <= three_hundred_nu

    assert three_hundred_nu > two_hundred_nu > one_hundred_nu
    assert three_hundred_nu >= two_hundred_nu >= one_hundred_nu

    assert (one_hundred_nu + two_hundred_nu) == three_hundred_nu
    assert (three_hundred_nu - two_hundred_nu) == one_hundred_nu

    difference = one_nu - one_nu_wei
    assert not difference == zero_nu

    actual = float(difference.to_tokens())
    expected = 0.999999999999999999
    assert actual == expected

    # 3.14 NU is 3_140_000_000_000_000_000 NuNit
    pi_nuweis = NU(3.14, 'NU')
    assert NU('3.14', 'NU') == pi_nuweis.to_nunits() == NU(3_140_000_000_000_000_000, 'NuNit')

    # Mixed type operations
    difference = NU('3.14159265', 'NU') - NU(1.1, 'NU')
    assert difference == NU('2.04159265', 'NU')

    result = difference + one_nu_wei
    assert result == NU(2041592650000000001, 'NuNit')

    # Similar to stake read + metadata operations in Staker
    collection = [one_hundred_nu, two_hundred_nu, three_hundred_nu]
    assert sum(collection) == NU('600', 'NU') == NU(600, 'NU') == NU(600.0, 'NU') == NU(600e+18, 'NuNit')

    #
    # Fractional Inputs
    #

    # A decimal amount of NuNit (i.e., a fraction of a NuNit)
    pi_nuweis = NU('3.14', 'NuNit')
    assert pi_nuweis == three_nu_wei  # Floor

    # A decimal amount of NU, which amounts to NuNit with decimals
    pi_nus = NU('3.14159265358979323846', 'NU')
    assert pi_nus == NU(3141592653589793238, 'NuNit')  # Floor

    # Positive Infinity
    with pytest.raises(NU.InvalidAmount):
        _inf = NU(float('infinity'), 'NU')

    # Negative Infinity
    with pytest.raises(NU.InvalidAmount):
        _neg_inf = NU(float('-infinity'), 'NU')

    # Not a Number
    with pytest.raises(InvalidOperation):
        _nan = NU(float('NaN'), 'NU')

    # Rounding NUs
    assert round(pi_nus, 2) == NU("3.14", "NU")
    assert round(pi_nus, 1) == NU("3.1", "NU")
    assert round(pi_nus, 0) == round(pi_nus) == NU("3", "NU")
