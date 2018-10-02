from bytestring_splitter import VariableLengthBytestring


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        self.host = host
        self.port = int(port)

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b":")
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)
