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

from typing import Callable

from web3.gas_strategies import time_based
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.main import Web3
from web3.types import TxParams, Wei

from nucypher.utilities.datafeeds import Datafeed, EtherchainGasPriceDatafeed, UpvestGasPriceDatafeed


GAS_STRATEGIES = {'glacial': time_based.glacial_gas_price_strategy,  # 24h
                  'slow': time_based.slow_gas_price_strategy,  # 1h
                  'medium': time_based.medium_gas_price_strategy,  # 5m
                  'fast': time_based.fast_gas_price_strategy,  # 60s
                  }


class UnknownGasStrategy(KeyError):
    pass


def strategy_from_nickname(name: str) -> Callable:
    try:
        return GAS_STRATEGIES[name]
    except KeyError:
        raise UnknownGasStrategy(name)


def datafeed_fallback_gas_price_strategy(web3: Web3, transaction_params: TxParams = None) -> Wei:
    feeds = (EtherchainGasPriceDatafeed, UpvestGasPriceDatafeed)

    for gas_price_feed_class in feeds:
        try:
            gas_strategy = gas_price_feed_class.construct_gas_strategy()
            gas_price = gas_strategy(web3, transaction_params)
        except Datafeed.DatafeedError:
            continue
        else:
            return gas_price
    else:
        # Worst-case scenario, we get the price from the ETH node itself
        return rpc_gas_price_strategy(web3, transaction_params)
