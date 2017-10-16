from nkms.crypto import api as API


class EncryptingKeypair(object):
    """
    An EncryptingKeypair that uses ECIES.
    """

    def __init__(self, privkey: bytes = None, pubkey: bytes = None):
        """
        Initializes an EncryptingKeypair object.
        """
        self.privkey = privkey
        self.pubkey = pubkey
        # TODO: Generate KeyID as a keccak_digest of the pubkey.

    def gen_privkey(self, create_pubkey: bool = True):
        """
        Generates an ECIES secp256k1 private key.

        TODO: Throw an error if generating a privkey on a keypair that already
              has a privkey.

        :param create_pubkey: Create the pubkey or not?
        """
        self.privkey = API.ecies_gen_priv()
        if create_pubkey:
            self.pubkey = API.ecies_priv2pub(self.privkey)


class SigningKeypair(object):
    """
    A SigningKeypair that uses ECDSA.
    """

    def __init__(self, privkey: bytes = None, pubkey: bytes = None):
        """
        Initalizes a SigningKeypair object.
        """
        self.privkey = privkey
        self.pubkey = pubkey
        # TODO: Generate a KeyID as a keccak_digest of the pubkey,

    def gen_privkey(self, create_pubkey: bool = True):
        """
        Generates an ECDSA secp256k1 private key.

        TODO: Throw an error if generating a privkey on a keypair that already
              has a privkey.
        TODO: See issue #77 on Github.

        :param create_pubkey: Create the pubkey or not?
        """
        self.privkey = API.ecdsa_gen_priv()
        if create_pubkey:
            self.pubkey = API.ecdsa_priv2pub(self.privkey)
