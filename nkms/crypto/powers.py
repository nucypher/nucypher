from random import SystemRandom
from typing import Iterable

from py_ecc.secp256k1 import N, privtopub

from nkms.crypto import api
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
        msg_digest = b"".join(api.keccak_digest(m) for m in messages)

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
        v, r, s = api.ecdsa_sign(msghash, self.priv_key)
        return api.ecdsa_gen_sig(v, r, s)

    def public_key(self):
        return self.pub_key


class EncryptingKeypair(CryptoPowerUp):
    KEYSIZE = 32
    confers_public_key = True

    def __init__(self, privkey=None):
        self.pre = umbral.PRE()

        if not privkey:
            self.priv_key = self.pre.gen_priv()
        else:
            self.priv_key = privkey
        self._pub_key = None

    @property
    def pub_key(self):
        if self._pub_key is None:
            self._pub_key = self.pre.priv2pub(self.priv_key)
        return self._pub_key

    def generate_key(self, pubkey=None):
        """
        Generate a raw symmetric key and its encrypted counterpart.

        :rtype: Tuple(bytes, bytes)
        :return: Tuple of the raw encrypted key and the encrypted key
        """
        pubkey = pubkey or self.pub_key
        symm_key, enc_symm_key = self.pre.encapsulate(pubkey)
        return (symm_key, enc_symm_key)

    def decrypt_key(self, enc_key, privkey=None):
        """
        Decrypts an ECIES encrypted symmetric key.

        :param int enc_key: The ECIES encrypted key as an integer
        :param bytes privkey: The privkey to decapsulate from

        :rtype: int
        :return: Decrypted key as an integer
        """
        priv_key = privkey or self.priv_key
        return self.pre.decapsulate(priv_key, enc_key)

    def rekey(self, privkey_a, privkey_b):
        """
        Generates a re-encryption key in interactive mode.

        :param bytes privkey_a: Alice's private key
        :param bytes privkey_b: Bob's private key (or an ephemeral privkey)

        :rtype: bytes
        :return: Bytestring of a re-encryption key
        """
        return self.pre.rekey(privkey_a, privkey_b)

    def split_rekey(self, privkey_a, privkey_b, min_shares, num_shares):
        """
        Generates key shares that can be used to re-encrypt data. Requires
        `min_shares` to be able to successfully combine data for full key.

        :param int privkey_a: Alice's private key
        :param int privkey_b: Bob's private key (or an ephemeral privkey)
        :param int min_shares: Threshold of shares needed to reconstruct key
        :param int num_shares: Total number of shares to generate

        :rtype: List(RekeyFrag)
        :return: List of `num_shares` RekeyFrags
        """
        return self.pre.split_rekey(privkey_a, privkey_b, min_shares,
                                    num_shares)

    def combine(self, shares):
        """
        Reconstructs a secret from the given shares.

        :param list shares: List of secret share fragments.

        :rtype: EncryptedKey
        :return: EncryptedKey from `shares`
        """
        # TODO: What to do if not enough shares, or invalid?
        return self.pre.combine(shares)

    def reencrypt(self, reenc_key, ciphertext):
        """
        Re-encrypts the provided ciphertext for the recipient of the generated
        re-encryption key.

        :param bytes reenc_key: The re-encryption key from the proxy to Bob
        :param bytes ciphertext: The ciphertext to re-encrypt to Bob

        :rtype: bytes
        :return: Re-encrypted ciphertext
        """
        return self.pre.reencrypt(reenc_key, ciphertext)

    def public_key(self):
        return self.pub_key
