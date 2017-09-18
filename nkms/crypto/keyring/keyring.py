import sha3
from nkms.crypto.keyring.keys import SigningKeypair


class KeyRing(object):
    def __init__(self, sig_keypair=None, enc_keypair=None):
        self.sig_keypair = SigningKeypair(sig_keypair)
        if not enc_keypair:
            # Generate encryption keypair
            # TODO: Create an encryption_keypair
            pass
        self.enc_keypair = enc_keypair

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
