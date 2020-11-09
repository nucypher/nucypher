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

from nucypher.utilities.gas_strategies import construct_fixed_price_gas_strategy


def test_fixed_price_gas_strategy():

    strategy = construct_fixed_price_gas_strategy(gas_price=42)

    assert 42 == strategy("web3", "tx")
    assert 42 == strategy("web3", "tx")
    assert 42 == strategy("web3", "tx")
    assert "0gwei" == strategy.name

    strategy = construct_fixed_price_gas_strategy(gas_price=12.34, denomination="gwei")

    assert 12340000000 == strategy("web3", "tx")
    assert 12340000000 == strategy("web3", "tx")
    assert 12340000000 == strategy("web3", "tx")
    assert "12gwei" == strategy.name
