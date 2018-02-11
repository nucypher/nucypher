import sha3

from typing import Union

from nkms.crypto import api as API
from umbral.keys import UmbralPrivateKey, UmbralPublicKey
from umbral import umbral
from nkms.crypto.kits import MessageKit


class Keypair(object):
    """
    A parent Keypair class for all types of Keypairs.
    """
    def __init__(self,
                umbral_key: Union[UmbralPrivateKey, UmbralPublicKey]=None,
                generate_keys_if_needed=True):
        """
        Initalizes a Keypair object with an Umbral key object.

        :param umbral_key: An UmbralPrivateKey or UmbralPublicKey
        :param generate_keys_if_needed: Generate keys or not?
        """
        try:
            self.pubkey = umbral_key.get_pub_key()
            self.privkey = umbral_key
        except NotImplementedError:
            self.pubkey = umbral_key
        except AttributeError:
            # They didn't pass anything we recognize as a valid key.
            if generate_keys_if_needed:
                self.privkey = UmbralPrivateKey.gen_key()
                self.pubkey = self.priv_key.get_pub_key()
            else:
                raise ValueError("Either pass a valid key as umbral_key or, if you want to generate keys, set generate_keys_if_needed to True.")

    def serialize_pubkey(self, as_b64=False) -> bytes:
        """
        Serializes the pubkey for storage/transport in either urlsafe base64
        or as a bytestring.

        :param as_bytes: Return the pubkey as bytes?

        :return: The serialized pubkey in bytes
        """
        if as_b64:
            return self.pubkey.save_key()
        return bytes(self.pubkey)

    def get_fingerprint(self):
        """
        Hashes the key using keccak-256 and returns the hexdigest in bytes.

        :return: Hexdigest fingerprint of key (keccak-256) in bytes
        """
        return sha3.keccak_256(bytes(self.pubkey)).hex_digest().encode()


class EncryptingKeypair(Keypair):
    """
    A keypair for Umbral
    """
    def decrypt(self, message_kit: MessageKit) -> bytes:
        """
        Decrypt data encrypted with Umbral.

        :param message_kit: A KMS MessageKit.

        :return: bytes
        """
        return message_kit.decypt(self.privkey)


class SigningKeypair(Keypair):
    """
    A SigningKeypair that uses ECDSA.
    """
    def sign(self, message: bytes) -> bytes:
        """
        Signs a hashed message and returns a signature.

        :param msghash: The hashed message to sign

        :return: Signature in bytes
        """
        return API.ecdsa_sign(message, self.privkey)
