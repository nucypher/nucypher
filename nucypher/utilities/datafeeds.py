from abc import ABC, abstractmethod
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Optional

import requests
from constant_sorrow.constants import FAST, FASTEST, MEDIUM, SLOW
from web3 import Web3
from web3.types import Wei


class Datafeed(ABC):

    class DatafeedError(RuntimeError):
        """Base class for exceptions concerning Datafeeds"""

    name = NotImplemented
    api_url = NotImplemented  # TODO: Deal with API keys

    def _probe_feed(self):
        try:
            response = requests.get(self.api_url)
        except requests.exceptions.ConnectionError as e:
            error = f"Failed to probe feed at {self.api_url}: {str(e)}"
            raise self.DatafeedError(error)

        if response.status_code != 200:
            error = f"Failed to probe feed at {self.api_url} with status code {response.status_code}"
            raise self.DatafeedError(error)

        self._raw_data = response.json()

    def __repr__(self):
        return f"{self.name} ({self.api_url})"


@dataclass
class GasFeePricing:
    max_priority_fee: Wei
    max_fee: Wei
    block: int


class EthereumGasPriceDatafeed(Datafeed):
    """Base class for Ethereum gas price data feeds"""

    _speed_names = NotImplemented
    _default_speed = NotImplemented

    _speed_equivalence_classes = {
        SLOW: ('slow', 'safeLow', 'low'),
        MEDIUM: ('medium', 'standard', 'average'),
        FAST: ('fast', 'high'),
        FASTEST: ('fastest', )
    }

    @abstractmethod
    def _parse_gas_fee_pricing(self, speed) -> GasFeePricing:
        return NotImplementedError

    def get_gas_fee_pricing(self, speed: Optional[str] = None) -> GasFeePricing:
        speed = speed or self._default_speed
        gas_fee_pricing = self._parse_gas_fee_pricing(self.get_canonical_speed(speed))
        return gas_fee_pricing

    @classmethod
    def get_canonical_speed(cls, speed: str):
        for canonical_speed, speed_names in cls._speed_equivalence_classes.items():
            if speed.lower() in map(str.lower, speed_names):
                return canonical_speed
        else:
            all_speed_names = [name for names in cls._speed_equivalence_classes.values() for name in names]
            suggestion = get_close_matches(speed, all_speed_names, n=1)
            if not suggestion:
                message = f"'{speed}' is not a valid speed name."
            else:
                suggestion = suggestion.pop()
                message = f"'{speed}' is not a valid speed name. Did you mean '{suggestion}'?"
            raise LookupError(message)


class PolygonGasStationDatafeed(EthereumGasPriceDatafeed):
    """
    Gas price datafeed from Polygon Gas Station.
    See https://docs.polygon.technology/tools/gas/polygon-gas-station/
    """
    _speed_names = {
        SLOW: "safeLow",
        MEDIUM: "standard",
        FAST: "fast",
        FASTEST: "fast",
    }
    _default_speed = 'fast'

    def _parse_suggestion(self, key) -> GasFeePricing:
        suggestion = self._raw_data[self._speed_names[key]]
        return GasFeePricing(
            max_priority_fee=Web3.to_wei(suggestion["maxPriorityFee"], "gwei"),
            max_fee=Web3.to_wei(suggestion["maxFee"], "gwei"),
            block=int(self._raw_data["blockNumber"]),
        )

    def _parse_gas_fee_pricing(self, speed) -> GasFeePricing:
        self._probe_feed()
        suggestion = self._parse_suggestion(speed)
        return suggestion


class PolygonMainnetGasStationDatafeed(PolygonGasStationDatafeed):
    chain_id = 137
    name = "Polygon Mainnet Gas Station datafeed"
    api_url = "https://gasstation.polygon.technology/v2"


class PolygonMumbaiGasStationDatafeed(PolygonGasStationDatafeed):
    chain_id = 80001
    name = "Polygon Mumbai Gas Station datafeed"
    api_url = "https://gasstation-testnet.polygon.technology/v2"
