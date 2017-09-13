import msgpack
import os
from nacl.utils import random
from nkms.crypto import default_algorithm, symmetric_from_algorithm


class EncryptedFile(object):
    def __init__(self, key, path, mode='rb'):
        self.path = path
        self.mode = mode

        cipher = symmetric_from_algorithm(default_algorithm)
        self.cipher = cipher(key)

    def _build_header(self, version=100, nonce=None, keys=None,
                      chunk_size=1000000, num_chunks=0, msg_len=0)
        """
        Builds a header and returns the msgpack encoded form of it.

        :param int version: Version of the NuCypher header
        :param bytes nonce: Nonce to write to header, default is random(20)
        :param list keys: Keys to write to header
        :param int chunk_size: Size of each chunk in bytes, default is 1MB
        :param int num_chunks: Number of chunks in ciphertext, default is 0
        :param int msg_len: Length of the encrypted ciphertext in total

        :return: (header_length, encoded_header)
        :rtype: Tuple(int, bytes)
        """
        if not nonce:
            nonce = random(20)

        self.header = {
            'version': version,
            'nonce': nonce,
            'keys': keys,
            'chunk_size': chunk_size,
            'num_chunks': num_chunks,
            'msg_len': msg_len,
        }

        try:
            encoded_header = msgpack.dumps(self.header)
        except ValueError as e:
            raise e
        self.header_length = len(encoded_header)
        return (self.header_length, encoded_header)

    def _update_header(self, header):
        """
        Updates the self.header with the key/values in header, then updates
        the header length.

        :param dict header: Dict to update self.header with

        :return: (header_length, encoded_header)
        :rtype: Tuple(int, bytes)
        """
        self.header.update(header)
        try:
            encoded_header = msgpack.dumps(self.header)
        except ValueError as e:
            raise e
        self.header_length = len(encoded_header)
        return (self.header_length, encoded_header)

    def _read_header(self):
        """
        Reads the header from the self.file_obj.
        """
        # Read last four bytes (header length) of file.
        self.file_obj.seek(-4, os.SEEK_END)

        # The first four bytes of the file are the header length
        self.header_length = int.from_bytes(
                                 self.file_obj.read(4), byteorder='big')
        # Seek to the beginning of the header and read it
        self.file_obj.seek(-(self.header_length + 4), os.SEEK_END)
        try:
            self.header = msgpack.loads(self.file_obj.read(self.header_length))
        except ValueError as e:
            raise e
        else:
            # Seek to the end of the ciphertext
            self.file_obj.seek(-(self.header_length + 4), os.SEEK_END)

    def _read_chunk(self, chunk_size, nonce):
        """
        Reads a chunk and decrypts/authenticates it.

        :param int chunk_size: Size of chunk to read from self.file_obj
        :param bytes nonce: Nonce to use during decryption

        :return: Decrypted/Authenticated chunk
        :rtype: Bytes
        """
        ciphertext = self.file_obj.read(chunk_size)
        return self.cipher.decrypt(ciphertext, nonce=nonce)

    def open(self, is_new=False):
        """
        Opens a file for Encryption/Decryption.

        :param bool is_new: Is the file new (and empty)?
        """
        self.file_obj = open(self.path, mode=self.mode)

        # file_obj is now ready for reading/writing encrypted data
        if not is_new:
            self._read_header()

    def read(self, num_chunks=0):
        """
        Reads num_chunks of encrypted ciphertext and decrypt/authenticate it.

        :param int num_chunks: Number of chunks to read. Default is all chunks

        :return: List of decrypted/authenticated ciphertext chunks
        :rtype: List
        """
        if num_chunks == 0:
            num_chunks = self.header['chunks']

        chunks = []
        for chunk_num in range(num_chunks):
            nonce = (self.header['nonce']
                     + chunk_num.to_bytes(4, byteorder='big'))
            chunks.append(self._read_chunk(self.header['chunk_size'], nonce))
        return chunks

    #def write(self, data, chunk_size=1000000):
    #    """
    #    Writes encrypted data to self.file_obj.

    #    :param bytes data: Data to encrypt and write
    #    
    #    :return: Number of chunks written
