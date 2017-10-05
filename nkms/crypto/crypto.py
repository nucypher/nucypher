from npre import umbral
from npre import elliptic_curve
from nacl.secret import SecretBox
from typing import Tuple, Union


class Crypto(object):
    PRE = umbral.PRE()

    @staticmethod
    def priv_bytes2ec(
        privkey: bytes
    ) -> elliptic_curve.Element:
        """
        Turns a private key, in bytes, into an elliptic_curve.Element.

        :param privkey: Private key to turn into an elliptic_curve.Element.

        :return: elliptic_curve.Element
        """
        return elliptic_curve.deserialize(Crypto.PRE.ecgroup, b'\x00' + privkey)

    @staticmethod
    def pub_bytes2ec(
        pubkey: bytes,
    ) -> elliptic_curve.Element:
        """
        Turns a public key, in bytes, into an elliptic_curve.Element.

        :param pubkey: Public key to turn into an elliptic_curve.Element.

        :return: elliptic_curve.Element
        """
        return elliptic_curve.deserialize(Crypto.PRE.ecgroup, b'\x01' + pubkey)

    @staticmethod
    def symm_encrypt(
        key: bytes,
        plaintext: bytes
    ) -> bytes:
        """
        Performs symmetric encryption using nacl.SecretBox.

        :param key: Key to encrypt with
        :param plaintext: Plaintext to encrypt

        :return: Encrypted ciphertext
        """
        cipher = SecretBox(key)
        return cipher.encrypt(plaintext)

    @staticmethod
    def symm_decrypt(
        key: bytes,
        ciphertext: bytes
    ) -> bytes:
        """
        Decrypts ciphertext performed with nacl.SecretBox.

        :param key: Key to decrypt with
        :param ciphertext: Nacl.SecretBox ciphertext to decrypt

        :return: Decrypted Plaintext
        """
        cipher = SecretBox(key)
        return cipher.decrypt(ciphertext)

    @staticmethod
    def ecies_gen_priv(
        to_bytes: bool = True
    ) -> Union[bytes, elliptic_curve.Element]:
        """
        Generates an ECIES private key.

        :param to_bytes: Return the byte serialization of the privkey?

        :return: An ECIES private key
        """
        privkey = Crypto.PRE.gen_priv()
        if to_bytes:
            return elliptic_curve.serialize(privkey)[1:]
        return privkey

    @staticmethod
    def ecies_priv2pub(
        privkey: Union[bytes, elliptic_curve.Element],
        to_bytes: bool = True
    ) -> Union[bytes, elliptic_curve.Element]:
        """
        Takes a private key (secret bytes or an elliptic_curve.Element) and
        derives the Public key from it.

        :param privkey: The Private key to derive the public key from
        :param to_bytes: Return the byte serialization of the pubkey?

        :return: The Public component of the Private key provided
        """
        if type(privkey) == bytes:
            privkey = Crypto.priv_bytes2ec(privkey)

        pubkey = Crypto.PRE.priv2pub(privkey)
        if to_bytes:
            return elliptic_curve.serialize(pubkey)[1:]
        return pubkey

    @staticmethod
    def ecies_encapsulate(
        pubkey: Union[bytes, elliptic_curve.Element],
    ) -> Tuple[bytes, umbral.EncryptedKey]:
        """
        Encapsulates an ECIES generated symmetric key for a public key.

        :param pubkey: Pubkey to generate a key for

        :return: Generated key in bytes, and EncryptedKey
        """
        if type(pubkey) == bytes:
            pubkey = Crypto.pub_bytes2ec(pubkey)
        pubkey = elliptic_curve.deserialize(Crypto.PRE.ecgroup, pubkey)
        return Crypto.PRE.encapsulate(pubkey)

    @staticmethod
    def ecies_decapsulate(
        privkey: Union[bytes, elliptic_curve.Element],
        enc_key: umbral.EncryptedKey
    ) -> bytes:
        """
        Decapsulates an ECIES generated encrypted key with a private key.

        :param privkey: Private key to decrypt the key with
        :param enc_key: Encrypted Key to decrypt

        :return: Decrypted symmetric key
        """
        if type(privkey) == bytes:
            privkey = Crypto.priv_bytes2ec(privkey)
        return Crypto.PRE.decapsulate(privkey, enc_key)
