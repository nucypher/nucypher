from nkms.crypto import default_algorithm, pre_from_algorithm


class EncryptingKeypair(object):
    def __init__(self, privkey_bytes=None):
        self.pre = pre_from_algorithm(default_algorithm)

        if not privkey_bytes:
            self.priv_key = self.pre.gen_priv(dtype='bytes')
        else:
            self.priv_key = privkey_bytes
        self.pub_key = self.pre.priv2pub(self.priv_key)

    def encrypt(self, data):
        """
        Encrypts the data provided.

        :param bytes data: The data to encrypt

        :rtype: bytes
        :return: Encrypted ciphertext
        """
        return self.pre.encrypt(self.pub_key, data)

    def decrypt(self, enc_data):
        """
        Decrypts the data provided

        :param bytes enc_data: Decrypts the data provided

        :rtype: bytes
        :return: Decrypted plaintext
        """
        return self.pre.decrypt(self.priv_key, enc_data)
