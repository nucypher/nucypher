from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.crypto.signing import SignatureStamp
from nucypher.utilities.logging import Logger


class NodeStorage:
    _TYPE_LABEL = 'storage_type'
    _name = ':memory:'

    class NodeStorageError(Exception):
        pass

    class UnknownNode(NodeStorageError):
        pass

    def __init__(self, character_class=None):
        self.__metadata = dict()
        from nucypher.characters.lawful import Ursula
        self.character_class = character_class or Ursula
        self.log = Logger(self.__class__.__name__)

    def __getitem__(self, item):
        return self.get(checksum_address=item)

    def __setitem__(self, key, value):
        return self.set(node=value)

    def __iter__(self):
        return self.all()

    def all(self) -> set:
        return set(self.__metadata.values())

    @validate_checksum_address
    def get(self, host: str = None, stamp: SignatureStamp = None):
        if not bool(stamp) ^ bool(host):
            message = "Either pass stamp or host; Not both. Got ({} {})".format(stamp, host)
            raise ValueError(message)
        try:
            return self.__metadata[stamp or host]
        except KeyError:
            raise self.UnknownNode

    def set(self, node) -> bytes:
        self.__metadata[node.stamp] = node
        return self.__metadata[node.stamp]

    def clear(self) -> None:
        """Forget all stored nodes and certificates"""
        self.__metadata = dict()
