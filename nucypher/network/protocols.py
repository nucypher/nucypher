"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from urllib.parse import urlparse

from eth_utils import is_checksum_address

from bytestring_splitter import VariableLengthBytestring


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


def parse_node_uri(uri: str):
    from nucypher.config.characters import UrsulaConfiguration

    if '@' in uri:
        checksum_address, uri = uri.split("@")
        if not is_checksum_address(checksum_address):
            raise ValueError("{} is not a valid checksum address.".format(checksum_address))
    else:
        checksum_address = None  # federated

    parsed_uri = urlparse(uri)

    if not parsed_uri.scheme:
        try:
            parsed_uri = urlparse('https://'+uri)
        except Exception:
            raise  # TODO: Do we need even deeper handling/validation here?

    if not parsed_uri.scheme == "https":
        raise ValueError("Invalid teacher scheme or protocol. Is the hostname prefixed with 'https://' ?")

    hostname = parsed_uri.hostname
    port = parsed_uri.port or UrsulaConfiguration.DEFAULT_REST_PORT
    return hostname, port, checksum_address


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        loopback, localhost = '127.0.0.1', 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b':', 1)
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

    def __repr__(self):
        return self.uri
