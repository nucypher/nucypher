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


from web3.gas_strategies import time_based

from nucypher.blockchain.eth.interfaces import BlockchainInterface


def test_get_gas_strategy():

    # Testing Web3's bundled time-based gas strategies
    bundled_gas_strategies = {'glacial': time_based.glacial_gas_price_strategy,  # 24h
                              'slow': time_based.slow_gas_price_strategy,  # 1h
                              'medium': time_based.medium_gas_price_strategy,  # 5m
                              'fast': time_based.fast_gas_price_strategy  # 60s
                              }
    for gas_strategy_name, expected_gas_strategy in bundled_gas_strategies.items():
        gas_strategy = BlockchainInterface.get_gas_strategy(gas_strategy_name)
        assert expected_gas_strategy == gas_strategy
        assert callable(gas_strategy)

    # Passing a callable gas strategy
    callable_gas_strategy = time_based.glacial_gas_price_strategy
    assert callable_gas_strategy == BlockchainInterface.get_gas_strategy(callable_gas_strategy)

    # Passing None should retrieve the default gas strategy
    assert BlockchainInterface.DEFAULT_GAS_STRATEGY == 'fast'
    default = bundled_gas_strategies[BlockchainInterface.DEFAULT_GAS_STRATEGY]
    gas_strategy = BlockchainInterface.get_gas_strategy()
    assert default == gas_strategy
