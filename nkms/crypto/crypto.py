from npre import umbral
from npre import elliptic_curve
from nacl.secret import SecretBox
from typing import Tuple, Union, List


class Crypto(object):
    PRE = umbral.PRE()

    @staticmethod
    def priv_bytes2ec(
        privkey: bytes
    ) -> elliptic_curve.ec_element:
        """
        Turns a private key, in bytes, into an elliptic_curve.ec_element.

        :param privkey: Private key to turn into an elliptic_curve.ec_element.

        :return: elliptic_curve.ec_element
        """
        return elliptic_curve.deserialize(Crypto.PRE.ecgroup, b'\x00' + privkey)

    @staticmethod
    def pub_bytes2ec(
        pubkey: bytes,
    ) -> elliptic_curve.ec_element:
        """
        Turns a public key, in bytes, into an elliptic_curve.ec_element.

        :param pubkey: Public key to turn into an elliptic_curve.ec_element.

        :return: elliptic_curve.ec_element
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
    ) -> Union[bytes, elliptic_curve.ec_element]:
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
        privkey: Union[bytes, elliptic_curve.ec_element],
        to_bytes: bool = True
    ) -> Union[bytes, elliptic_curve.ec_element]:
        """
        Takes a private key (secret bytes or an elliptic_curve.ec_element) and
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
        pubkey: Union[bytes, elliptic_curve.ec_element],
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
        privkey: Union[bytes, elliptic_curve.ec_element],
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

    @staticmethod
    def ecies_rekey(
        privkey_a: Union[bytes, elliptic_curve.ec_element],
        privkey_b: Union[bytes, elliptic_curve.ec_element],
        to_bytes: bool = True
    ) -> Union[bytes, umbral.RekeyFrag]:
        """
        Generates a re-encryption key from privkey_a to privkey_b.

        :param privkey_a: Private key to re-encrypt from
        :param privkey_b: Private key to re-encrypt to
        :param to_bytes: Format result as bytes?

        :return: Re-encryption key
        """
        if type(privkey_a) == bytes:
            privkey_a = Crypto.priv_bytes2ec(privkey_a)
        if type(privkey_b) == bytes:
            privkey_b = Crypto.priv_bytes2ec(privkey_b)

        rk = Crypto.PRE.rekey(privkey_a, privkey_b)
        if to_bytes:
            return elliptic_curve.serialize(rk.key)
        return rk

    @staticmethod
    def ecies_split_rekey(
        privkey_a: Union[bytes, elliptic_curve.ec_element],
        privkey_b: Union[bytes, elliptic_curve.ec_element],
        min_shares: int,
        total_shares: int
    ) -> List[umbral.RekeyFrag]:
        """
        Performs a split-key re-encryption key generation where a minimum
        number of shares `min_shares` are required to reproduce a rekey.
        Will split a rekey into `total_shares`.

        :param privkey_a: Privkey to re-encrypt from
        :param privkey_b: Privkey to re-encrypt to
        :param min_shares: Minimum shares needed to reproduce rekey
        :param total_shares: Total shares to generate from split-rekey gen

        :return: A list of RekeyFrags to distribute
        """
        if type(privkey_a) == bytes:
            privkey_a = Crypto.priv_bytes2ec(privkey_a)
        if type(privkey_b) == bytes:
            privkey_b = Crypto.priv_bytes2ec(privkey_b)
        return Crypto.PRE.split_rekey(privkey_a, privkey_b,
                                      min_shares, total_shares)

    @staticmethod
    def ecies_combine(
        encrypted_keys: List[umbral.EncryptedKey]
    ) -> umbral.EncryptedKey:
        """
        Combines the encrypted keys together to form a rekey from split_rekey.

        :param encrypted_keys: Encrypted keys to combine

        :return: The combined EncryptedKey of the rekey
        """
        return Crypto.PRE.combine(encrypted_keys)

    @staticmethod
    def ecies_reencrypt(
        rekey: Union[bytes, umbral.RekeyFrag],
        enc_key: Union[bytes, umbral.EncryptedKey],
    ) -> umbral.EncryptedKey:
        """
        Re-encrypts the key provided.

        :param rekey: Re-encryption key to use
        :param enc_key: Encrypted key to re-encrypt

        :return: The re-encrypted key
        """
        if type(rekey) == bytes:
            rekey = umbral.RekeyFrag(None, Crypto.priv_bytes2ec(rekey))
        if type(enc_key) == bytes:
            enc_key = umbral.EncryptedKey(Crypto.priv_bytes2ec(enc_key), None)
        return Crypto.PRE.reencrypt(rekey, enc_key)
