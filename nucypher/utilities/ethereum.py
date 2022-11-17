from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_constructor_abi, merge_args_and_kwargs
from web3._utils.contracts import encode_abi
from web3.contract import ContractConstructor


def encode_constructor_arguments(web3: Web3,
                                 constructor_function: ContractConstructor,
                                 *constructor_args, **constructor_kwargs) -> HexStr:
    """
    Takes a web3 constructor function and the arguments passed to it, and produces an encoding hex string
    of the constructor arguments, following the standard ABI encoding conventions.
    If there's no constructor, it returns None.
    """
    constructor_abi = get_constructor_abi(constructor_function.abi)
    if constructor_abi:
        arguments = merge_args_and_kwargs(constructor_abi, constructor_args, constructor_kwargs)
        data = encode_abi(web3, constructor_abi, arguments)
    else:
        data = None
    return data


def connect_web3_provider(eth_provider_uri: str) -> None:
    """
    Convenience function for connecting to an ethereum provider now.
    This may be used to optimize the startup time of some applications by
    establishing the connection eagerly.
    """
    from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory

    if not BlockchainInterfaceFactory.is_interface_initialized(eth_provider_uri=eth_provider_uri):
        BlockchainInterfaceFactory.initialize_interface(eth_provider_uri=eth_provider_uri)
    interface = BlockchainInterfaceFactory.get_interface(eth_provider_uri=eth_provider_uri)
    interface.connect()
