import msgpack
from nacl.utils import random


class Header(object):
    def __init__(self, header_path=None, header={}):
        """
        Initializes a header object that contains metadata about a storage
        object (ie: EncryptedFile)

        :param bytes/string header_path: Path to the file containing the header
        :param dict header: Header params to use when building the header
        """
        if header_path:
            self.header = self._read_header(header_path)
        else:
            self.header = self._build_header(**header)

    def _read_header(self, header_path):
        """
        Reads the header file located at `header_path` and loads it from its
        msgpack format into the self.header dict.

        :param bytes/string header_path: The path to the header file

        :return: The loaded dict from the header file
        :rtype: Dict
        """
        with open(header_path, mode='rb') as f:
            # TODO: Use custom Exception (invalid or corrupt header)
            try:
                header = msgpack.loads(f.read())
            except ValueError as e:
                raise e
        return header

    def _build_header(self, version=100, nonce=None, keys=None,
                      chunk_size=1000000, num_chunks=0):
        """
        Builds a header and sets the header dict in the `Header` object.

        :param int version: Version of the NuCypher header
        :param bytes nonce: Nonce to write to header, default is random(20)
        :param list keys: Keys to write to header
        :param int chunk_size: Size of each chunk in bytes, default is 1MB
        :param int num_chunks: Number of chunks in ciphertext

        :return: dict of header
        :rtype: Dict
        """
        if not nonce:
            nonce = random(20)

        return {
            'version': version,
            'nonce': nonce,
            'keys': keys,
            'chunk_size': chunk_size,
            'num_chunks': num_chunks,
        }

    def _write_header(self, header_path):
        """
        Writes the msgpack dumped self.header dict to the file located at
        `header_path`.

        :param string/bytes header_path: The path to write the msgpack dumped
            header to
        """
        with open(header_path, mode='wb') as f:
            try:
                f.write(msgpack.dumps(self.header))
            except ValueError as e:
                raise e

    def update_header(self, header={}):
        """
        Updates the self.header dict with the dict in header.

        :param dict header: Values to use in the dict.update call
        """
        self.header.update(header)
