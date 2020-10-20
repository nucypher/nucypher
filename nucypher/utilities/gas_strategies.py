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
import datetime
import functools
from typing import Callable

from web3 import Web3
from web3.exceptions import ValidationError
from web3.gas_strategies import time_based
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.types import Wei, TxParams

from nucypher.utilities.datafeeds import Datafeed, EtherchainGasPriceDatafeed, UpvestGasPriceDatafeed


class GasStrategyError(RuntimeError):
    """
    Generic exception when retrieving a gas price using a gas strategy
    """

#
# Datafeed gas strategies
#


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


#
# Web3 gas strategies
#

__RAW_WEB3_GAS_STRATEGIES = {
    'slow': time_based.slow_gas_price_strategy,      # 1h
    'medium': time_based.medium_gas_price_strategy,  # 5m
    'fast': time_based.fast_gas_price_strategy       # 60s
}


def wrap_web3_gas_strategy(web3_gas_strategy: Callable):
    """
    Enriches the web3 exceptions thrown by gas strategies
    """
    @functools.wraps(web3_gas_strategy)
    def _wrapper(*args, **kwargs):
        try:
            return web3_gas_strategy(*args, **kwargs)
        except ValidationError as e:
            raise GasStrategyError("Calling the web3 gas strategy failed, probably due to an unsynced chain.") from e
    return _wrapper


WEB3_GAS_STRATEGIES = {speed: wrap_web3_gas_strategy(strategy) for speed, strategy in __RAW_WEB3_GAS_STRATEGIES.items()}

EXPECTED_CONFIRMATION_TIME_IN_SECONDS = {
    'slow': int(datetime.timedelta(hours=1).total_seconds()),
    'medium': int(datetime.timedelta(minutes=5).total_seconds()),
    'fast': 60
}
