from random import SystemRandom
from typing import Iterable

from py_ecc.secp256k1 import N, privtopub, ecdsa_raw_sign, ecdsa_raw_recover

from nkms.crypto import api
from nkms.crypto.keypairs import EncryptingKeypair


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
            raise TypeError("power_up must be a subclass of CryptoPowerUp or an instance of a subclass of CryptoPowerUp.")
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()  # TODO: Make this an ID for later lookup on a KeyStore.


    def pubkey_sig_bytes(self):
        try:
            return self._power_ups[SigningKeypair].pubkey_bytes()  # TODO: Turn this into an ID lookup on a KeyStore.
        except KeyError:
            raise NoSigningPower
    def pubkey_sig_tuple(self):
        try:
            return self._power_ups[SigningKeypair].pub_key  # TODO: Turn this into an ID lookup on a KeyStore.
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
