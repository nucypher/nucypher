from _typeshed import SupportsAnext
from typing import TypeVar, Any, Awaitable

from typing_extensions import ParamSpec


def connect_web3_provider(blockchain_endpoint: str) -> None:
    """
    Convenience function for connecting to a blockchain provider now.
    This may be used to optimize the startup time of some applications by
    establishing the connection eagerly.
    """
    from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory

    if not BlockchainInterfaceFactory.is_interface_initialized(
        endpoint=blockchain_endpoint
    ):
        BlockchainInterfaceFactory.initialize_interface(endpoint=blockchain_endpoint)
    interface = BlockchainInterfaceFactory.get_interface(endpoint=blockchain_endpoint)
    interface.connect()


_SupportsAnextT = TypeVar("_SupportsAnextT", bound=SupportsAnext[Any], covariant=True)
_AwaitableT = TypeVar("_AwaitableT", bound=Awaitable[Any])
_AwaitableT_co = TypeVar("_AwaitableT_co", bound=Awaitable[Any], covariant=True)
_P = ParamSpec("_P")
