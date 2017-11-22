from typing import Tuple

from nacl.secret import SecretBox

from nkms.crypto import api as API
from nkms.keystore import constants
from npre import umbral
from npre import elliptic_curve as ec


class Keypair(object):

    public_only = False

    # TODO: Throw error if a key is called and it doesn't exist
    # TODO: Maybe write a custome error ofr ^?

    def __init__(self, privkey: bytes = None, pubkey: "PublicKey" = None) -> None:
        if privkey and pubkey:
            self.privkey, self.pubkey = privkey, pubkey
        elif not privkey and not pubkey:
            # Neither key is provided; we'll generate.
            self.gen_privkey(create_pubkey=True)
        elif privkey and not pubkey:
            # We have the privkey; use it to generate the pubkey.
            self.privkey = privkey
            self._gen_pubkey()
        elif pubkey and not privkey:
            # We have only the pubkey; this is a public-only pair.
            self.pubkey = PublicKey(pubkey)
            self.public_only = True

    @staticmethod
    def deserialize_key(key_data: bytes) -> 'Keypair':
        """
        Deserialize the key_data into a Keypair object.

        :param key_data: Serialized key data from a keypair object

        :return: Keypair object
        """
        keypair_byte = key_data[0].to_bytes(1, 'big')
        key_type_byte = key_data[1].to_bytes(1, 'big')
        key = key_data[2:]

        if keypair_byte == constants.ENC_KEYPAIR_BYTE:
            if key_type_byte == constants.PUB_KEY_BYTE:
                return EncryptingKeypair(pubkey=key)

            elif key_type_byte == constants.PRIV_KEY_BYTE:
                return EncryptingKeypair(privkey=key)

        elif keypair_byte == constants.SIG_KEYPAIR_BYTE:
            if key_type_byte == constants.PUB_KEY_BYTE:
                return SigningKeypair(pubkey=key_data)  # Kinda weird for the moment - we're using all 66 bytes here.  TODO: Decide whether to make this the norm.

            elif key_type_byte == constants.PRIV_KEY_BYTE:
                return SigningKeypair(privkey=key)
        else:
            raise ValueError("Unable to determine which type of keypair this is - keypair_byte was {}".format(keypair_byte))


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
            self._gen_pubkey()

    def _gen_pubkey(self):
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
                ekey=ec.deserialize(API.PRE.ecgroup, ekey[0]), re_id=ekey[1])
        if privkey is None:
            privkey = self._priv_key
        else:
            privkey = ec.deserialize(API.PRE.ecgroup, privkey)

        key = self.pre.decapsulate(privkey, ekey)
        cipher = SecretBox(key)
        return cipher.decrypt(edata)

    def serialize_pubkey(self) -> bytes:
        """
        Serializes the pubkey for storage.

        :return: The serialized pubkey in bytes
        """
        serialized_key = (constants.ENC_KEYPAIR_BYTE +
                          constants.PUB_KEY_BYTE +
                          self.pubkey)
        return serialized_key

    def serialize_privkey(self) -> bytes:
        """
        Serializes the privkey for storage.

        :return: The serialized privkey in bytes
        """
        serialized_key = (constants.ENC_KEYPAIR_BYTE +
                          constants.PRIV_KEY_BYTE +
                          self.privkey)
        return serialized_key


class SigningKeypair(Keypair):
    """
    A SigningKeypair that uses ECDSA.
    """

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
            self._gen_pubkey()

    def _gen_pubkey(self):
        self.pubkey = PublicKey(API.ecdsa_priv2pub(self.privkey))

    def sign(self, msghash: bytes) -> bytes:
        """
        Signs a hashed message and returns a signature.

        :param msghash: The hashed message to sign

        :return: Signature in bytes
        """
        v, r, s = API.ecdsa_sign(msghash, self.privkey)
        return API.ecdsa_gen_sig(v, r, s)

    def verify(self, msghash: bytes, signature: bytes) -> bool:
        """
        Verifies that a signature came from this keypair.

        :param msghash: Hashed message used in the signature
        :param signature: Signature of the hashed message

        :return: Boolean if the signature is valid
        """
        v, r, s = API.ecdsa_load_sig(signature)
        return API.ecdsa_verify(v, r, s, msghash, self.pubkey.without_metabytes())

    def serialize_pubkey(self) -> bytes:
        """
        Serializes the pubkey for storage.

        :return: The serialized pubkey in bytes
        """
        serialized_key = (constants.SIG_KEYPAIR_BYTE +
                          constants.PUB_KEY_BYTE +
                          self.pubkey)
        return serialized_key

    def serialize_privkey(self) -> bytes:
        """
        Serializes the privkey for storage.

        :return: The serialized privkey in bytes
        """
        serialized_key = (constants.SIG_KEYPAIR_BYTE +
                          constants.PRIV_KEY_BYTE +
                          self.privkey)
        return serialized_key


class PublicKey(bytes):
    _EXPECTED_LENGTH = 66
    _METABYTES_LENGTH = 2

    def without_metabytes(self):
        return self[self._METABYTES_LENGTH::]