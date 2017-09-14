import io
from nkms.storage import Header
from nacl.utils import random
from nkms.crypto import default_algorithm, symmetric_from_algorithm


class EncryptedFile(object):
    def __init__(self, key, path, header_path):
        """
        Creates an EncryptedFile object that allows the user to encrypt or
        decrypt data into a file defined at `path`.

        An EncryptedFile object actually is composed of two files:
        1) The ciphertext -- This is the chunked and encrypted ciphertext
        2) The header -- This contains the metadata of the ciphertext that
            tells us how to decrypt it, or add more data.

        :param bytes key: Symmetric key to use for encryption/decryption
        :param bytes path: Path of ciphertext file to open
        :param bytes header_path: Path of header file
        """
        self.path = path
        self.header_path = header_path
        self.header_obj = Header(self.header_path)

        cipher = symmetric_from_algorithm(default_algorithm)
        self.cipher = cipher(key)

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

    @property
    def header(self):
        return self.header_obj.header

    def open_new(self, keys, chunk_size=1000000, nonce=None):
        """
        Opens a new EncryptedFile and creates a header for it ready for
        writing encrypted data.

        :param list keys: Encrypted keys to put in the header.
        :param int chunk_size: Size of encrypted chunks in bytes, default is 1MB
        :param bytes nonce: 20 byte Nonce to use for encryption
        """
        self.file_obj = open(self.path, mode=self.mode)
        self._build_header(nonce=nonce, keys=keys, chunk_size=chunk_size)

    def open(self, is_new=False):
        """
        Opens a file for Encryption/Decryption.

        :param bool is_new: Is the file new (and empty)?
        """
        # TODO: Error if self.file_obj is already defined
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

    def write(self, data):
        """
        Writes encrypted data to self.file_obj.

        :param bytes data: Data to encrypt and write
        :param int chunk_num: Chunk number to start writing at

        :return: Number of chunks written
        :rtype: int
        """
        # Always start off at the last chunk_num
        chunk_num = self.header['num_chunks']
        buf_data = io.BytesIO(data)

        plaintext = buf_data.read(self.header['chunk_size'])
        while len(plaintext) > 0:
            nonce = (self.header['nonce']
                     + chunk_num.to_bytes(4, byteorder='big'))
            enc_msg = self.cipher.encrypt(plaintext, nonce=nonce)
            self.file_obj.write(enc_msg.ciphertext)
            plaintext = buf_data.read(self.header['chunk_size'])
            chunk_num += 1
        self._update_header({'num_chunks': chunk_num})

    def close(self):
        """
        Writes the header to the filesystem and closes the file_obj.
        """
        self.header.update_header()
        self.file_obj.close()
