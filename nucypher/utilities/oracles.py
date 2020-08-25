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
from abc import ABC, abstractmethod
from typing import Optional

import requests
from web3 import Web3
from web3.gas_strategies.rpc import rpc_gas_price_strategy
from web3.types import Wei, TxParams


class Oracle(ABC):

    class OracleError(RuntimeError):
        """Base class for Oracle-related exceptions"""

    name = NotImplemented
    api_url = NotImplemented  # TODO: Deal with API keys

    def _probe_oracle(self):
        try:
            response = requests.get(self.api_url)
        except requests.exceptions.ConnectionError as e:
            error = f"Failed to probe oracle at {self.api_url}: {str(e)}"
            raise self.OracleError(error)

        if response.status_code != 200:
            error = f"Failed to probe oracle at {self.api_url} with status code {response.status_code}"
            raise self.OracleError(error)

        self._raw_data = response.json()

    def __repr__(self):
        return f"{self.name} ({self.api_url})"


class EthereumGasPriceOracle(Oracle):
    """Base class for Ethereum gas price oracles"""

    _speed_names = NotImplemented
    _default_speed = NotImplemented

    @abstractmethod
    def _parse_gas_prices(self):
        return NotImplementedError

    def get_gas_price(self, speed: Optional[str] = None) -> Wei:
        speed = speed or self._default_speed
        self._parse_gas_prices()
        gas_price_wei = Wei(self.gas_prices[speed])
        return gas_price_wei

    @classmethod
    def construct_gas_strategy(cls):
        def oracle_based_gas_price_strategy(web3: Web3, transaction_params: TxParams = None) -> Wei:
            oracle = cls()
            gas_price = oracle.get_gas_price()
            return gas_price
        return oracle_based_gas_price_strategy


class EtherchainGasPriceOracle(EthereumGasPriceOracle):
    """Gas price oracle from Etherchain"""

    name = "Etherchain oracle"
    api_url = "https://www.etherchain.org/api/gasPriceOracle"
    _speed_names = ('safeLow', 'standard', 'fast', 'fastest')
    _default_speed = 'fast'

    def _parse_gas_prices(self):
        self._probe_oracle()
        self.gas_prices = {k: int(Web3.toWei(v, 'gwei')) for k, v in self._raw_data.items()}


class UpvestGasPriceOracle(EthereumGasPriceOracle):
    """Gas price oracle from Upvest"""

    name = "Upvest oracle"
    api_url = "https://fees.upvest.co/estimate_eth_fees"
    _speed_names = ('slow', 'medium', 'fast', 'fastest')
    _default_speed = 'fastest'

    def _parse_gas_prices(self):
        self._probe_oracle()
        self.gas_prices = {k: int(Web3.toWei(v, 'gwei')) for k, v in self._raw_data['estimates'].items()}


def oracle_fallback_gas_price_strategy(web3: Web3, transaction_params: TxParams = None) -> Wei:
    oracles = (EtherchainGasPriceOracle, UpvestGasPriceOracle)

    for gas_price_oracle_class in oracles:
        try:
            gas_strategy = gas_price_oracle_class.construct_gas_strategy()
            gas_price = gas_strategy(web3, transaction_params)
        except Oracle.OracleError:
            continue
        else:
            return gas_price
    else:
        # Worst-case scenario, we get the price from the ETH node itself
        return rpc_gas_price_strategy(web3, transaction_params)



# TODO: We can implement here other oracles, like the ETH/USD (e.g., https://api.coinmarketcap.com/v1/ticker/ethereum/)
# suggested in a comment in nucypher.blockchain.eth.interfaces.BlockchainInterface#sign_and_broadcast_transaction
