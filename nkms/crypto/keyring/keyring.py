import sha3
from nkms.crypto.keyring.keys import SigningKeypair, EncryptingKeypair


class KeyRing(object):
    def __init__(self, sig_privkey=None, enc_privkey=None):
        """
        Initializes a KeyRing object. Uses the private keys to initialize
        their respective objects, if provided. If not, it will generate new
        keypairs.

        :param bytes sig_privkey: Private key in bytes of ECDSA signing keypair
        :param bytes enc_privkey: Private key in bytes of encrypting keypair
        """
        self.sig_keypair = SigningKeypair(sig_privkey)
        self.enc_keypair = EncryptingKeypair(enc_privkey)

    def sign(self, message):
        """
        Signs a message and returns a signature with the keccak hash.

        :param bytes message: Message to sign in bytes

        :rtype: bytestring
        :return: Signature of message
        """
        msg_digest = sha3.keccak_256(message).digest()
        return self.sig_keypair.sign(msg_digest)

    def verify(self, message, signature):
        """
        Verifies a signature.

        :param bytes message: Message to check signature for
        :param bytes signature: Signature to validate

        :rtype: Boolean
        :return: Is the message signature valid or not?
        """
        msg_digest = sha3.keccak_256(message).digest()
        return self.sig_keypair.verify(msg_digest, signature)

    def encrypt(self, plaintext):
        """
        Encrypts the plaintext provided.

        :param bytes plaintext: Plaintext to encrypt w/ EncryptingKeypair

        :rtype: bytes
        :return: Ciphertext of plaintext
        """
        return self.enc_keypair.encrypt(plaintext)

    def decrypt(self, ciphertext):
        """
        Decrypts the ciphertext provided.

        :param bytes ciphertext: Ciphertext to decrypt w/ EncryptingKeypair

        :rtype: bytes
        :return: Plaintext of Encrypted ciphertext
        """
        return self.enc_keypair.decrypt(ciphertext)
