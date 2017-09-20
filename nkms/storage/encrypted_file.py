import io
import os
from nkms.storage.header import Header
from nkms.storage.constants import NONCE_COUNTER_BYTE_SIZE, PADDING_LENGTH
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
        cipher = symmetric_from_algorithm(default_algorithm)
        self.cipher = cipher(key)

        # Opens the header file and parses it, if it exists. If not, creates it
        self.header_path = header_path
        self.header_obj = Header(self.header_path)

        self.path = path

        # Always seek the beginning of the file on first open
        self.file_obj = open(self.path, mode='a+b')
        self.file_obj.seek(0)

    @property
    def header(self):
        return self.header_obj.header

    def _read_chunk(self, chunk_size, nonce):
        """
        Reads a chunk and decrypts/authenticates it.

        :param int chunk_size: Size of chunk to read from self.file_obj
        :param bytes nonce: Nonce to use during decryption

        :return: Decrypted/Authenticated chunk
        :rtype: Bytes
        """
        ciphertext = self.file_obj.read(chunk_size + PADDING_LENGTH)
        return self.cipher.decrypt(ciphertext, nonce=nonce)

    def read(self, num_chunks=0):
        """
        Reads num_chunks of encrypted ciphertext and decrypt/authenticate it.

        :param int num_chunks: Number of chunks to read. When set to 0, it will
            read the all the chunks and decrypt them.

        :return: List of decrypted/authenticated ciphertext chunks
        :rtype: List
        """
        if not num_chunks:
            num_chunks = self.header[b'num_chunks']

        chunks = []
        for chunk_num in range(num_chunks):
            nonce = (self.header[b'nonce']
                     + chunk_num.to_bytes(NONCE_COUNTER_BYTE_SIZE,
                                          byteorder='big'))
            chunks.append(self._read_chunk(self.header[b'chunk_size'], nonce))
        return chunks

    def write(self, data):
        """
        Writes encrypted data to self.file_obj.

        :param bytes data: Data to encrypt and write
        :param int chunk_num: Chunk number to start writing at

        :return: Number of chunks written
        :rtype: int
        """
        # Always start writing at the end of the file, never overwrite.
        self.file_obj.seek(0, os.SEEK_END)

        # Start off at the last chunk_num
        chunk_num = self.header[b'num_chunks']

        buf_data = io.BytesIO(data)

        chunks_written = 0
        plaintext = buf_data.read(self.header[b'chunk_size'])
        while len(plaintext) > 0:
            nonce = (self.header[b'nonce']
                     + chunk_num.to_bytes(NONCE_COUNTER_BYTE_SIZE,
                                          byteorder='big'))
            enc_data = self.cipher.encrypt(plaintext, nonce=nonce)
            self.file_obj.write(enc_data.ciphertext)
            chunks_written += 1

            plaintext = buf_data.read(self.header[b'chunk_size'])
            chunk_num += 1
        self.header_obj.update_header({b'num_chunks': chunk_num})
        return chunks_written

    def close(self):
        """
        Writes the header to the filesystem and closes the file_obj.
        """
        self.header_obj.update_header()
        self.file_obj.close()
