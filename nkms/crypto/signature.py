from nkms.crypto import api as API


class Signature(object):
    """
    The Signature object allows signatures to be made and verified.
    """

    def __init__(self, v: int=None, r: int=None, s: int=None, sig: bytes=None):
        """
        Initializes a Signature object.

        :param v: V param of signature
        :param r: R param of signature
        :param s: S param of signature

        :return: Signature object
        """
        if sig:
            v, r, s = API.ecdsa_load_sig(sig)

        self.v = v
        self.r = r
        self.s = s

    def verify(self, message: bytes, pubkey: bytes) -> bool:
        """
        Verifies that a message's signature was valid.

        :param message: The message to verify
        :param pubkey: Pubkey of the signer

        :return: True if valid, False if invalid
        """
        msg_digest = API.keccak_digest(message)
        return API.ecdsa_verify(self.v, self.r, self.s, msg_digest, pubkey)

    def __bytes__(self):
        """
        Implements the __bytes__ call for Signature to transform into a
        transportable mode.
        """
        return API.ecdsa_gen_sig(self.v, self.r, self.s)
