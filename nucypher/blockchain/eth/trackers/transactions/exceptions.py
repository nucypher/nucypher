from web3.types import RPCError, TxParams

from nucypher.blockchain.eth.trackers.transactions.utils import txtracker_log


class TransactionFinalized(Exception):
    """raised when a transaction has been included in a block"""


class InsufficientFunds(RPCError):
    """raised when a transaction exceeds the spending cap"""


def _handle_rpc_error(e: Exception, tx: TxParams) -> None:
    error = RPCError(**e.args[0])
    txtracker_log.critical(
        f"Transaction #{tx['nonce']} failed with {error['code']} | {error['message']}"
    )
    if error["code"] == -32000:
        if "insufficient funds" in error["message"]:
            raise InsufficientFunds
