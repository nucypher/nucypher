from web3.types import RPCError


class TransactionFinalized(Exception):
    """raised when a transaction has been included in a block"""


class InsufficientFunds(RPCError):
    """raised when a transaction exceeds the spending cap"""


class StrategyLimitExceeded(Exception):
    """raised when a transaction exceeds a strategy limitation"""


class TransactionReverted(Exception):
    """raised when a transaction has been reverted"""
