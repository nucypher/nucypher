from nkms.crypto import api as API


class Keypair(object):

    public_only = False

    def __init__(self, privkey: bytes = None, pubkey: bytes = None):
        if privkey and pubkey:
            self.privkey, self.pubkey = privkey, pubkey
        elif not privkey and not pubkey:
            # Neither key is provided; we'll generate.
            self.privkey, self.pubkey = API.generate_random_keypair()
        elif privkey and not pubkey:
            # We have the privkey; use it to generate the pubkey.
            self.privkey = privkey
            self.pubkey = API.privtopub(privkey)
        elif pubkey and not privkey:
            # We have only the pubkey; this is a public-only pair.
            self.public_only = True


class EncryptingKeypair(Keypair):
    """
    An EncryptingKeypair that uses ECIES.
    """

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
