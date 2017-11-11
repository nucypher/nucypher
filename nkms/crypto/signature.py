from nkms.crypto import api as API


class Signature(bytes):
    """
    The Signature object allows signatures to be made and verified.
    """
    _EXPECTED_LENGTH = 65

    def __init__(self, sig_as_bytes: bytes=None, v: int=None, r: int=None, s: int=None):
        """
        Initializes a Signature object.

        :param v: V param of signature
        :param r: R param of signature
        :param s: S param of signature

        :return: Signature object
        """
        if sig_as_bytes and any((v, r, s)):
            raise ValueError("Pass *either* sig_as_bytes *or* v, r, and s - don't pass both.")
        if not any ((sig_as_bytes, v, r, s)):
            raise ValueError("Pass either sig_as_bytes or v, r, and s.")

        if sig_as_bytes:
            v, r, s = API.ecdsa_load_sig(sig_as_bytes)

        self._v = v
        self._r = r
        self._s = s

    def __repr__(self):
        return "{} v{}: {} - {}".format(__class__.__name__, self._v, self._r, self._s)

    def verify(self, message: bytes, pubkey: bytes) -> bool:
        """
        Verifies that a message's signature was valid.

        :param message: The message to verify
        :param pubkey: Pubkey of the signer

        :return: True if valid, False if invalid
        """
        msg_digest = API.keccak_digest(message)
        return API.ecdsa_verify(self._v, self._r, self._s, msg_digest, pubkey)

    def __bytes__(self):
        """
        Implements the __bytes__ call for Signature to transform into a
        transportable mode.
        """
        return API.ecdsa_gen_sig(self._v, self._r, self._s)
