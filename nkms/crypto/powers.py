from random import SystemRandom
from typing import Iterable, Union, List, Tuple

from py_ecc.secp256k1 import N, privtopub

from nkms.crypto import API as API
from nkms.keystore import keypairs
from npre import umbral


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
                SigningKeypair].pubkey_bytes()  # TODO: Turn this into an ID lookup on a KeyStore.
        except KeyError:
            raise NoSigningPower

    def pubkey_sig_tuple(self):
        try:
            return self._power_ups[
                SigningKeypair].pub_key  # TODO: Turn this into an ID lookup on a KeyStore.
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

    def encrypt_for(self, pubkey_sign_id, cleartext):
        try:
            enc_keypair = self._power_ups[EncryptingKeypair]
            # TODO: Actually encrypt.
        except KeyError:
            raise NoEncryptingPower


class CryptoPowerUp(object):
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False


class SigningKeypair(CryptoPowerUp):
    confers_public_key = True

    def __init__(self, privkey_bytes=None):
        self.secure_rand = SystemRandom()
        if privkey_bytes:
            self.priv_key = privkey_bytes
        else:
            # Key generation is random([1, N - 1])
            priv_number = self.secure_rand.randrange(1, N)
            self.priv_key = priv_number.to_bytes(32, byteorder='big')
        # Get the public component
        self.pub_key = privtopub(self.priv_key)

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

    def __init__(self, keypair: keypairs.EncryptingKeypair):
        """
        Initalizes an EncryptingPower object for CryptoPower.
        """
        self.keypair = keypair
        self.priv_key = keypair.privkey
        self.pub_key = keypair.pubkey

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
        data_key: bytes,
        path_key: bytes,
    ) -> bytes:
        """
        Encrypts the data key with the path keys provided.

        :param data_key: Symmetric data key to encrypt
        :param path_keys: Path keys to encrypt the data_key with

        :return: List[Tuple[enc_key_data, enc_key_path]]
        """
        plain_key_data, enc_key_path = API.ecies_encaspulate(path_key)
        enc_key_data = API.symm_encrypt(plain_key_data, data_key)
        return (enc_key_data, enc_key_path)

    def _decrypt_key(
        self,
        enc_data_key: bytes,
        enc_path_key: bytes,
        priv_key: bytes
    ) -> bytes:
        """
        Decrypts the enc_data_key via ECIES decapsulation.

        TODO: Name these params better

        :param enc_data_key: Encrypted key to decrypt
        :param enc_path_key: ECIES encapsulated key
        :param priv_key: Private key to use in ECIES decapsulate

        :return: decrypted key
        """
        dec_symm_key = API.ecies_decapsulate(priv_key, enc_path_key)
        return API.symm_decrypt(dec_symm_key, enc_data_key)

    def encrypt(
        self,
        data: bytes,
        recp_keypair: keypairs.EncryptingKeypair,
        M: int,
        N: int,
        path: bytes = None
    ) -> Tuple[Tuple[bytes, bytes, bytes], bytes, List[umbral.RekeyFrag]]:
        """
        Encrypts data using ECIES.

        :param data: Data to encrypt
        :param path: Path to derive pathkey(s) for
        :param recp_keypair: Recipient's EncryptingKeypair
        :param M: Minimum number of kFrags needed to complete ciphertext
        :param N: Total number of kFrags to generate.
        :param path: Path of file to generate pathkey(s) for

        :return: Tuple((enc_data, enc_eph_key), enc_data_key, reenc_frags)
        """
        # Encrypt plaintext data with nacl.SecretBox (symmetric)
        data_key = API.secure_random(EncryptingPower.KEYSIZE)
        enc_data = API.symm_encrypt(data_key, data)

        # Derive path keys, if path. If not, use our public key
        if path:
            path_priv, path_pub = self._derive_path_key(path)
        else:
            path_priv = self.priv_key
            path_pub = self.pub_key

        # Encrypt the data key with the path keys
        enc_data_key = self._encrypt_key(data_key, path_pub)

        # Generate ephemeral key and create a re-encryption key
        eph_priv_key = API.ecies.gen_priv()
        reenc_frags = API.ecies_split_rekey(path_priv, eph_priv_key, M, N)

        # Encrypt the ephemeral key for Bob
        enc_eph_key = self._encrypt_key(eph_priv_key, recp_keypair.pubkey)

        return ((enc_data, enc_eph_key), enc_data_key, reenc_frags)

    def decrypt(
        self,
        enc_data: bytes,
        enc_eph_key: bytes,
        key_frags: List[umbral.EncryptedKey]
    ) -> bytes:
        """
        Decrypts data using the ECIES scheme.

        :param enc_data: Encrypted data to decrypt
        :param enc_eph_key: The encrypted ephemeral key
        :param key_frags: Re-encryption keyfrags to combine.

        :return: Decrypted data
        """
        pass
