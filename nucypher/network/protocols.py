from typing import Tuple
from urllib.parse import urlparse

from eth_typing import Address
from eth_utils import is_checksum_address

from nucypher.utilities.networking import LOOPBACK_ADDRESS


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


def parse_node_uri(uri: str, delimiter: str = "@") -> Tuple[str, int, Address]:
    from nucypher.config.characters import UrsulaConfiguration

    checksum_address = None
    if delimiter in uri:
        checksum_address, uri = uri.split(delimiter)
        if checksum_address is None:
            raise ValueError(f"{uri} is not a valid Teacher URI - no checksum address.")
        if not is_checksum_address(checksum_address):
            raise ValueError("{} is not a valid checksum address.".format(checksum_address))

    #############################################
    # Strange logic here to ensure https:// - possibly pursuant to https://bugs.python.org/msg179670
    # It's not clear that there is any version of python 3.7+ that requires this, so we may
    # be able to drop it in the near future.
    if not uri.startswith("https://"):
        uri = "https://" + uri
    #############################################

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

    def __init__(self, host, port) -> None:
        loopback, localhost = LOOPBACK_ADDRESS, 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    def __iter__(self):
        yield self.host
        yield self.port

    @property
    def uri(self):
        return u"{}:{}".format(self.host, self.port)

    @property
    def formal_uri(self):
        return u"{}://{}".format('https', self.uri)

    def __repr__(self):
        return self.uri
