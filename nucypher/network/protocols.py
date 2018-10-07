from bytestring_splitter import VariableLengthBytestring
from constant_sorrow import default_constant_splitter, constants
from kademlia.node import Node
from kademlia.protocol import KademliaProtocol

from nucypher.crypto.api import keccak_digest
from nucypher.network.routing import NucypherRoutingTable


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        loopback, localhost = '127.0.0.1', 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b":")
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    @property
    def uri(self):
        return u"{}:{}".format(self.host, self.port)

    @property
    def formal_uri(self):
        return u"{}://{}".format('https', self.uri)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)
