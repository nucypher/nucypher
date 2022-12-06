from decimal import Decimal
from typing import Union

from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID
from eth_utils import is_address, is_hex, to_checksum_address
from web3 import Web3
from web3.contract import ContractConstructor, ContractFunction

from nucypher.blockchain.eth.clients import PUBLIC_CHAINS


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
