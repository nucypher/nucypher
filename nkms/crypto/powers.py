import inspect
from typing import Iterable, List, Tuple

import umbral
from nkms.crypto import api as API
from nkms.crypto.kits import MessageKit
from nkms.keystore import keypairs
from nkms.keystore.keypairs import SigningKeypair, EncryptingKeypair
from umbral.keys import UmbralPublicKey, UmbralPrivateKey


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class NoEncryptingPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups=None, generate_keys_if_needed=False):
        self._power_ups = {}
        # TODO: The keys here will actually be IDs for looking up in a KeyStore.
        self.public_keys = {}
        self.generate_keys = generate_keys_if_needed

        if power_ups is not None:
            for power_up in power_ups:
                self.consume_power_up(power_up)
        else:
            power_ups = []  # default

    def consume_power_up(self, power_up):
        if isinstance(power_up, CryptoPowerUp):
            power_up_class = power_up.__class__
            power_up_instance = power_up
        elif CryptoPowerUp in inspect.getmro(power_up):
            power_up_class = power_up
            power_up_instance = power_up(
                generate_keys_if_needed=self.generate_keys)
        else:
            raise TypeError(
                ("power_up must be a subclass of CryptoPowerUp or an instance "
                 "of a subclass of CryptoPowerUp."))
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()

    def pubkey_sig_bytes(self):
        try:
            pubkey_sig = self._power_ups[SigningPower].public_key()
            return bytes(pubkey_sig)
        except KeyError:
            raise NoSigningPower

    def sign(self, message):
        """
        TODO: New docstring.
        """
        try:
            sig_keypair = self._power_ups[SigningPower]
        except KeyError as e:
            raise NoSigningPower(e)
        return sig_keypair.sign(message)

    def decrypt(self, ciphertext):
        try:
            encrypting_power = self._power_ups[EncryptingPower]
            return encrypting_power.decrypt(ciphertext)
        except KeyError:
            raise NoEncryptingPower

    def encrypt_for(self, enc_pubkey, plaintext):
        ciphertext, capsule = umbral.umbral.encrypt(enc_pubkey, plaintext)
        return MessageKit(ciphertext=ciphertext, capsule=capsule)


class CryptoPowerUp(object):
    """
    Gives you MORE CryptoPower!
    """
    confers_public_key = False


class KeyPairBasedPower(CryptoPowerUp):
    _keypair_class = keypairs.Keypair

    def __init__(self, keypair: keypairs.Keypair=None,
                 pubkey: UmbralPublicKey=None,
                 generate_keys_if_needed=True) -> None:
        if keypair and pubkey:
            raise ValueError(
                "Pass keypair or pubkey_bytes (or neither), but not both.")
        elif keypair:
            self.keypair = keypair
        else:
            # They didn't pass a keypair; we'll make one with the bytes (if any)
            # they provided.
            if pubkey:
                key_to_pass_to_keypair = pubkey
            else:
                # They didn't even pass pubkey_bytes.  We'll generate a keypair.
                key_to_pass_to_keypair = UmbralPrivateKey.gen_key()
            self.keypair = self._keypair_class(
                umbral_key=key_to_pass_to_keypair)


class SigningPower(KeyPairBasedPower):
    confers_public_key = True
    _keypair_class = SigningKeypair

    def sign(self, message):
        """
        Signs a message message and returns a Signature.
        """
        return self.keypair.sign(message)

    def public_key(self):
        return self.keypair.pubkey


class EncryptingPower(KeyPairBasedPower):
    confers_public_key = True
    _keypair_class = EncryptingKeypair
    KEYSIZE = 32

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
            pubkey: UmbralPublicKey=None
    ) -> Tuple[bytes, bytes]:
        """
        Encrypts the `key` provided for the provided `pubkey` using the ECIES
        schema. If no `pubkey` is provided, it uses `self.pub_key`.

        :param key: Key to encrypt
        :param pubkey: Public Key to encrypt the `key` for

        :return (encrypted key, Umbral Capsule)
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

    def decrypt(
            self,
            message_kit: MessageKit,
    ) -> bytes:
        cleartext = umbral.umbral.decrypt(message_kit.capsule, self.keypair.privkey,
                              message_kit.ciphertext, message_kit.alice_pubkey)

        return cleartext

    def public_key(self):
        return self.keypair.pubkey
