from web3.types import RPCError, TxParams

from nucypher.blockchain.eth.trackers.transactions.tx import FutureTx
from nucypher.blockchain.eth.trackers.transactions.utils import txtracker_log


class TransactionFinalized(Exception):
    """raised when a transaction has been included in a block"""


class InsufficientFunds(RPCError):
    """raised when a transaction exceeds the spending cap"""


class StrategyLimitExceeded(Exception):
    """raised when a transaction exceeds a strategy limitation"""


def _handle_rpc_error(e: Exception, tx: FutureTx) -> None:
    try:
        error = RPCError(**e.args[0])
    except TypeError:
        txtracker_log.critical(f"[error] transaction #atx-{tx.id}|{tx.params['nonce']} failed with {e}")
        return
    txtracker_log.critical(
        f"[error] transaction #atx-{tx.id}|{tx.params['nonce']} failed with {error['code']} | {error['message']}"
    )
    if error["code"] == -32000:
        if "insufficient funds" in error["message"]:
            raise InsufficientFunds
