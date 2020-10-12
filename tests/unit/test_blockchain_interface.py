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

from nucypher.blockchain.eth.gas_strategies import GAS_STRATEGIES, strategy_from_nickname, UnknownGasStrategy


def test_get_gas_strategy():

    # Testing Web3's bundled time-based gas strategies
    for gas_strategy_name, expected_gas_strategy in GAS_STRATEGIES.items():
        gas_strategy = GAS_STRATEGIES[gas_strategy_name]
        assert expected_gas_strategy == gas_strategy
        assert callable(gas_strategy)

    expected = GAS_STRATEGIES['fast']
    strategy = strategy_from_nickname('fast')
    assert strategy == expected

    with pytest.raises(UnknownGasStrategy):
        _strategy = strategy_from_nickname('llama-counting-gas-strategy')
