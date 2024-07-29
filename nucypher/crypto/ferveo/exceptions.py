class FerveoKeyMismatch(Exception):
    """
    Raised when a local ferveo public key does not match the
    public key published to the Coordinator.
    """
