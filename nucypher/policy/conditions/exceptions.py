# Lingo Validation Errors (Grammar)
class InvalidConditionLingo(Exception):
    """Invalid lingo grammar."""


class InvalidLogicalOperator(Exception):
    """Invalid definition of logical lingo operator."""


# Connectivity
class NoConnectionToChain(RuntimeError):
    """Raised when a node does not have an associated provider for a chain."""

    def __init__(self, chain: int):
        self.chain = chain
        message = f"No connection to chain ID {chain}"
        super().__init__(message)


class ReturnValueEvaluationError(Exception):
    """Issue with Return Value and Key"""


# Context Variable
class RequiredContextVariable(Exception):
    """No value provided for context variable"""


class InvalidContextVariableData(Exception):
    """Context variable could not be processed"""


class ContextVariableVerificationFailed(Exception):
    """Issue with using the provided context variable."""


# Conditions
class InvalidCondition(ValueError):
    """Invalid value for condition."""


class ConditionEvaluationFailed(Exception):
    """Could not evaluate condition."""


class RPCExecutionFailed(ConditionEvaluationFailed):
    """Raised when an exception is raised from an RPC call."""
