from web3.types import RPCError


class TransactionFinalized(Exception):
    """raised when a transaction has been included in a block"""


class InsufficientFunds(RPCError):
    """raised when a transaction exceeds the spending cap"""


class Halt(Exception):
    """
    Raised when a strategy exceeds a limitation.
    Used to mark a pending transaction as "wait, don't retry".
    """


class TransactionReverted(Exception):
    """raised when a transaction has been reverted"""
