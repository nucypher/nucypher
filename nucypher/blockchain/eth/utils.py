from decimal import Decimal
from typing import Union

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract.contract import ContractConstructor, ContractFunction


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
        amount_in_wei = Web3.to_wei(Decimal(amount), original_denomination)

        common_denominations = ('wei', 'gwei', 'ether')

        options = [str(Web3.from_wei(amount_in_wei, d)) for d in common_denominations]

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


def truncate_checksum_address(checksum_address: ChecksumAddress) -> str:
    return f"{checksum_address[:8]}...{checksum_address[-8:]}"
