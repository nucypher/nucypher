import msgpack


class Header(object):
    def __init__(self, header_path=None, header_dict=None):
        """
        Initializes a header object that contains metadata about a storage
        object (ie: EncryptedFile)

        :param bytes/string header_path: Path to the file containing the header
        """
        if header_path:
            self.header = self._read_header(header_path)
        else:
            # TODO: Build a header
            pass

    def _read_header(self, header_path):
        with open(header_path, mode='rb') as f:
            # TODO: Use custom Exception (invalid or corrupt header)
            try:
                header = msgpack.loads(f.read())
            except ValueError as e:
                raise e
        return header
