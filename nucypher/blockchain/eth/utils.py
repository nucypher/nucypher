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

from decimal import Decimal
from typing import Union

import maya
from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID
from eth_typing import BlockNumber
from eth_utils import is_address, is_hex, to_checksum_address
from web3 import Web3
from web3.contract import ContractConstructor, ContractFunction

from nucypher.blockchain.eth.clients import PUBLIC_CHAINS
from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS


def epoch_to_period(epoch: int, seconds_per_period: int) -> int:
    period = epoch // seconds_per_period
    return period


def datetime_to_period(datetime: maya.MayaDT, seconds_per_period: int) -> int:
    """Converts a MayaDT instance to a period number."""
    future_period = epoch_to_period(epoch=datetime.epoch, seconds_per_period=seconds_per_period)
    return int(future_period)


def period_to_epoch(period: int, seconds_per_period: int) -> int:
    epoch = period * seconds_per_period
    return epoch


def datetime_at_period(period: int, seconds_per_period: int, start_of_period: bool = False) -> maya.MayaDT:
    """
    Returns the datetime object at a given period, future, or past.
    If start_of_period, the datetime object represents the first second of said period.
    """
    if start_of_period:
        datetime_at_start_of_period = maya.MayaDT(epoch=period_to_epoch(period, seconds_per_period))
        return datetime_at_start_of_period
    else:
        now = maya.now()
        current_period = datetime_to_period(datetime=now, seconds_per_period=seconds_per_period)
        delta_periods = period - current_period
        target_datetime = now + maya.timedelta(seconds=seconds_per_period) * delta_periods
        return target_datetime


def calculate_period_duration(future_time: maya.MayaDT, seconds_per_period: int, now: maya.MayaDT = None) -> int:
    """Takes a future MayaDT instance and calculates the duration from now, returning in periods"""
    if now is None:
        now = maya.now()
    future_period = datetime_to_period(datetime=future_time, seconds_per_period=seconds_per_period)
    current_period = datetime_to_period(datetime=now, seconds_per_period=seconds_per_period)
    periods = future_period - current_period
    return periods


def estimate_block_number_for_period(period: int, seconds_per_period: int,  latest_block: BlockNumber) -> BlockNumber:
    """Logic for getting the approximate block height of the start of the specified period."""
    period_start = datetime_at_period(period=period,
                                      seconds_per_period=seconds_per_period,
                                      start_of_period=True)
    seconds_from_midnight = int((maya.now() - period_start).total_seconds())
    blocks_from_midnight = seconds_from_midnight // AVERAGE_BLOCK_TIME_IN_SECONDS

    block_number_for_period = latest_block - blocks_from_midnight
    return block_number_for_period


def etherscan_url(item, network: str, is_token=False) -> str:
    if network is None or network is UNKNOWN_DEVELOPMENT_CHAIN_ID:
        raise ValueError("A network must be provided")

    if network == PUBLIC_CHAINS[1]:  # Mainnet chain ID is 1
        domain = "https://etherscan.io"
    else:
        testnets_supported_by_etherscan = (PUBLIC_CHAINS[3],  # Ropsten
                                           PUBLIC_CHAINS[4],  # Rinkeby
                                           PUBLIC_CHAINS[5],  # Goerli
                                           PUBLIC_CHAINS[42],  # Kovan
                                           )
        if network in testnets_supported_by_etherscan:
            domain = f"https://{network.lower()}.etherscan.io"
        else:
            raise ValueError(f"'{network}' network not supported by Etherscan")

    if is_address(item):
        item_type = 'token' if is_token else 'address'
        item = to_checksum_address(item)
    elif is_hex(item) and len(item) == 2 + 32*2:  # If it's a hash...
        item_type = 'tx'
    else:
        raise ValueError(f"Cannot construct etherscan URL for {item}")

    url = f"{domain}/{item_type}/{item}"
    return url


def prettify_eth_amount(amount, original_denomination: str = 'wei') -> str:
    """
    Converts any ether `amount` in `original_denomination` and finds a suitable representation based on its length.
    The options in consideration are representing the amount in wei, gwei or ETH.
    :param amount: Input amount to prettify
    :param original_denomination: Denomination used by `amount` (by default, wei is assumed)
    :return: Shortest representation for `amount`, considering wei, gwei and ETH.
    """
    try:
        # First obtain canonical representation in wei. Works for int, float, Decimal and str amounts
        amount_in_wei = Web3.toWei(Decimal(amount), original_denomination)

        common_denominations = ('wei', 'gwei', 'ether')

        options = [str(Web3.fromWei(amount_in_wei, d)) for d in common_denominations]

        best_option = min(zip(map(len, options), options, common_denominations))
        _length, pretty_amount, denomination = best_option

        if denomination == 'ether':
            denomination = 'ETH'
        pretty_amount += " " + denomination

    except Exception:  # Worst case scenario, we just print the str representation of amount
        pretty_amount = str(amount)

    return pretty_amount


def get_transaction_name(contract_function: Union[ContractFunction, ContractConstructor]) -> str:
    deployment = isinstance(contract_function, ContractConstructor)
    try:
        transaction_name = contract_function.fn_name.upper()
    except AttributeError:
        transaction_name = 'DEPLOY' if deployment else 'UNKNOWN'
    return transaction_name
