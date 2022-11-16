


class CompilationError(RuntimeError):
    """
    Raised when there is a problem compiling nucypher contracts
    or with the expected compiler configuration.
    """


class ProgrammingError(RuntimeError):
    """Caused by a human error in code"""
