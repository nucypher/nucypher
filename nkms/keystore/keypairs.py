from typing import Tuple

from nacl.secret import SecretBox

from nkms.crypto import api as API
from npre import umbral


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

    def decrypt(self,
                edata: Tuple[bytes, bytes],
                privkey: bytes = None) -> bytes:
        """
        Decrypt data encrypted by ECIES
        edata = (ekey, edata)
            ekey is needed to reconstruct a DH secret
            edata encrypted by the block cipher
            privkey is optional private key if we want to use something else
            than what keypair uses
        """
        if isinstance(edata[0], tuple) and isinstance(edata[1], tuple):
            # In case it was re-encrypted data
            return self.decrypt_reencrypted(edata)

        ekey, edata = edata
        # When it comes to decrypt(), ekey[1] is always None
        # we could use that and save 2 bytes,
        # but it makes the code less readable
        ekey = umbral.EncryptedKey(
                ekey=ec.deserialize(self.pre.ecgroup, ekey[0]), re_id=ekey[1])
        if privkey is None:
            privkey = self._priv_key
        else:
            privkey = ec.deserialize(self.pre.ecgroup, privkey)

        key = self.pre.decapsulate(privkey, ekey)
        cipher = SecretBox(key)
        return cipher.decrypt(edata)


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
