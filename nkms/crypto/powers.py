from random import SystemRandom
from typing import Iterable, Union, List, Tuple

from py_ecc.secp256k1 import N, privtopub

from nkms.crypto import api as API
from nkms.keystore import keypairs
from nkms.keystore.keypairs import SigningKeypair as RealSigingKeypair, EncryptingKeypair


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoEncryptingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups=[]):
        self._power_ups = {}
        self.public_keys = {}  # TODO: The keys here will actually be IDs for looking up in a KeyStore.

        if power_ups:
            for power_up in power_ups:
                self.consume_power_up(power_up)

    def consume_power_up(self, power_up):
        if isinstance(power_up, CryptoPowerUp):
            power_up_class = power_up.__class__
            power_up_instance = power_up
        elif CryptoPowerUp in power_up.__bases__:
            power_up_class = power_up
            power_up_instance = power_up()
        else:
            raise TypeError(
                "power_up must be a subclass of CryptoPowerUp or an instance of a subclass of CryptoPowerUp.")
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[
                power_up_class] = power_up_instance.public_key()  # TODO: Make this an ID for later lookup on a KeyStore.

    def pubkey_sig_bytes(self):
        try:
            return self._power_ups[
                SigningKeypair].pub_key  # TODO: Turn this into an ID lookup on a KeyStore.
        except KeyError:
            raise NoSigningPower

    def pubkey_sig_tuple(self):
        try:
            return API.ecdsa_bytes2pub(self._power_ups[
                SigningKeypair].pub_key)  # TODO: Turn this into an ID lookup on a KeyStore.
        except KeyError:
            raise NoSigningPower

    def sign(self, *messages):
        """
        Signs a message and returns a signature with the keccak hash.
        :param Iterable messages: Messages to sign in an iterable of bytes
        :rtype: bytestring
        :return: Signature of message
        """
        try:
            sig_keypair = self._power_ups[SigningKeypair]
        except KeyError:
            raise NoSigningPower
        msg_digest = b"".join(API.keccak_digest(m) for m in messages)

        return sig_keypair.sign(msg_digest)

    def decrypt(self, ciphertext):
        try:
            encrypting_power = self._power_ups[EncryptingPower]
            return encrypting_power.decrypt(ciphertext)
        except KeyError:
            raise NoEncryptingPower

    def encrypt_for(self, pubkey, cleartext):
        try:
            encrypting_power = self._power_ups[EncryptingPower]
            ciphertext = encrypting_power.encrypt(cleartext, bytes(pubkey))
            return ciphertext
        except KeyError:
            raise NoEncryptingPower


class CryptoPowerUp(object):
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False


class SigningKeypair(CryptoPowerUp):
    confers_public_key = True

    def __init__(self, keypair=None):  # TODO: Pretty much move this __init__ to SigningPower

        self.real_keypair = keypair or RealSigingKeypair()  # Total throwaway line - this will not be "real_keypair" because this will be in SigningPower
        self.real_keypair.gen_privkey()

        self.priv_key, self.pub_key = self.real_keypair.privkey, self.real_keypair.pubkey

    def pubkey_bytes(self):
        return b''.join(i.to_bytes(32, 'big') for i in self.pub_key)

    def sign(self, msghash):
        """
        TODO: Use crypto API sign()

        Signs a hashed message and returns a msgpack'ed v, r, and s.

        :param bytes msghash: Hash of the message

        :rtype: Bytestring
        :return: Msgpacked bytestring of v, r, and s (the signature)
        """
        v, r, s = API.ecdsa_sign(msghash, self.priv_key)
        return API.ecdsa_gen_sig(v, r, s)

    def public_key(self):
        return self.pub_key


class EncryptingPower(CryptoPowerUp):
    KEYSIZE = 32

    def __init__(self, keypair: keypairs.EncryptingKeypair = None):
        """
        Initalizes an EncryptingPower object for CryptoPower.
        """

        self.keypair = keypair or EncryptingKeypair()
        self.priv_key = self.keypair.privkey
        self.pub_key = self.keypair.pubkey

    def _split_path(self, path: bytes) -> List[bytes]:
        """
        Splits the file path provided and provides subpaths to each directory.

        :param path: Path to file

        :return: Subpath(s) from path
        """
        # Hacky workaround: b'/'.split(b'/') == [b'', b'']
        if path == b'/':
            return [b'']

        dirs = path.split(b'/')
        return [b'/'.join(dirs[:i + 1]) for i in range(len(dirs))]

    def _derive_path_key(
        self,
        path: bytes,
    ) -> bytes:
        """
        Derives a key for the specific path.

        :param path: Path to derive key for

        :return: Derived key
        """
        priv_key = API.keccak_digest(self.priv_key, path)
        pub_key = API.ecies_priv2pub(priv_key)
        return (priv_key, pub_key)

    def _encrypt_key(
            self,
            key: bytes,
            pubkey: bytes = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypts the `key` provided for the provided `pubkey` using the ECIES
        schema. If no `pubkey` is provided, it uses `self.pub_key`.

        :param key: Key to encrypt
        :param pubkey: Public Key to encrypt the `key` for

        :return (encrypted key, encapsulated ECIES key)
        """
        pubkey = pubkey or self.pub_key

        symm_key, enc_symm_key = API.ecies_encaspulate(pubkey)
        enc_key = API.symm_encrypt(symm_key, key)
        return (enc_key, enc_symm_key)

    def _decrypt_key(
            self,
            enc_key: bytes,
            enc_symm_key: bytes,
            privkey: bytes = None
    ) -> bytes:
        """
        Decrypts the encapsulated `enc_key` with the `privkey`, if provided.
        If `privkey` is None, then it uses `self.priv_key`.

        :param enc_key: ECIES encapsulated key
        :param enc_symm_key: Symmetrically encrypted key
        :param privkey: Private key to decrypt with (if provided)

        :return: Decrypted key
        """
        privkey = privkey or self.priv_key

        dec_symm_key = API.ecies_decapsulate(privkey)
        return API.symm_decrypt(dec_symm_key, enc_symm_key)

    def gen_path_keys(
            self,
            path: bytes
    ) -> List[Tuple[bytes, bytes]]:
        """
        Generates path keys and returns path keys

        :param path: Path to derive key(s) from

        :return: List of path keys
        """
        subpaths = self._split_path(path)
        keys = []
        for subpath in subpaths:
            path_priv, path_pub = self._derive_path_key(subpath)
            keys.append((path_priv, path_pub))
        return keys

    def encrypt(
            self,
            data: bytes,
            pubkey: bytes = None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypts data with Public key encryption

        :param data: Data to encrypt
        :param pubkey: publc key to encrypt for

        :return: (Encrypted Key, Encrypted data)
        """
        pubkey = pubkey or self.pub_key

        key, enc_key = API.ecies_encapsulate(pubkey)
        enc_data = API.symm_encrypt(key, data)

        return (enc_data, API.elliptic_curve.serialize(enc_key.ekey))

    def decrypt(
            self,
            enc_data: Tuple[bytes, bytes],
            privkey: bytes = None
    ) -> bytes:
        """
        Decrypts data using ECIES PKE. If no `privkey` is provided, it uses
        `self.priv_key`.

        :param enc_data: Tuple: (encrypted data, ECIES encapsulated key)
        :param privkey: Private key to decapsulate with

        :return: Decrypted data
        """
        privkey = privkey or self.priv_key
        ciphertext, enc_key = enc_data

        enc_key = API.elliptic_curve.deserialize(API.PRE.ecgroup, enc_key)
        enc_key = API.umbral.EncryptedKey(ekey=enc_key, re_id=None)

        dec_key = API.ecies_decapsulate(privkey, enc_key)

        return API.symm_decrypt(dec_key, ciphertext)
