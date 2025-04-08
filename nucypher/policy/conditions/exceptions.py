# Lingo Validation Errors (Grammar)
class InvalidConditionLingo(Exception):
    """Invalid lingo grammar."""


# Connectivity
class NoConnectionToChain(RuntimeError):
    """Raised when a node does not have an associated provider for a chain."""

    def __init__(self, chain: int, message: str = None):
        self.chain = chain
        message = message or f"No connection to chain ID {chain}"
        super().__init__(message)


class InvalidConnectionToChain(RuntimeError):
    """Raised when a node does not have a valid provider for a chain."""

    def __init__(self, expected_chain: int, actual_chain: int, message: str = None):
        self.expected_chain = expected_chain
        self.actual_chain = actual_chain
        message = (
            message
            or f"Invalid blockchain connection; expected chain ID {expected_chain}, but detected {actual_chain}"
        )
        super().__init__(message)


class ReturnValueEvaluationError(Exception):
    """Issue with Return Value and Key"""


# Context Variable
class InvalidConditionContext(Exception):
    """Raised when invalid context is encountered."""


class RequiredContextVariable(InvalidConditionContext):
    """No value provided for context variable"""


class InvalidContextVariableData(InvalidConditionContext):
    """Context variable could not be processed"""


class ContextVariableVerificationFailed(InvalidConditionContext):
    """Issue with using the provided context variable."""


# Conditions
class InvalidCondition(ValueError):
    """Invalid value for condition."""


class ConditionEvaluationFailed(Exception):
    """Could not evaluate condition."""


class RPCExecutionFailed(ConditionEvaluationFailed):
    """Raised when an exception is raised from an RPC call."""


class JsonRequestException(ConditionEvaluationFailed):
    """Raised when an exception is raised from a JSON request."""


class JWTException(ConditionEvaluationFailed):
    """Raised when an exception is raised when validating a JWT token"""
