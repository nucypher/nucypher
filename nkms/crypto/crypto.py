from nacl.secret import SecretBox


class Crypto(object):
    @staticmethod
    def symm_encrypt(key: bytes, plaintext: bytes) -> bytes:
        cipher = SecretBox(key)
        return cipher.encrypt(plaintext)

    @staticmethod
    def symm_decrypt(key: bytes, ciphertext: bytes) -> bytes:
        cipher = SecretBox(key)
        return cipher.decrypt(ciphertext)
