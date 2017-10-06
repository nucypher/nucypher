from random import SystemRandom
from typing import Iterable

import msgpack
import sha3
from py_ecc.secp256k1 import N, privtopub, ecdsa_raw_sign, ecdsa_raw_recover

from nkms.crypto.keypairs import EncryptingKeypair


class PowerUpError(TypeError):
    pass


class NoSigningPower(PowerUpError):
    pass


class CryptoPower(object):
    def __init__(self, power_ups=[]):
        self._power_ups = {}
        self.public_keys = {}  # TODO: The keys here will actually be IDs for looking up in a KeyRing.

        for power_up in power_ups:
            self.consume_power_up(power_up)

    def consume_power_up(self, power_up):
        if isinstance(power_up, PowerUp):
            power_up_class = power_up.__class__
            power_up_instance = power_up
        elif PowerUp in power_up.__bases__:
            power_up_class = power_up
            power_up_instance = power_up()
        else:
            raise TypeError("power_up must be a subclass of PowerUp or an instance of a subclass of PowerUp.")
        self._power_ups[power_up_class] = power_up_instance

        if power_up.confers_public_key:
            self.public_keys[power_up_class] = power_up_instance.public_key()  # TODO: Make this an ID for later lookup on a KeyRing.


    def pubkey_sig_bytes(self):
        return self._power_ups[SigningKeypair].pubkey_bytes()  # TODO: Turn this into an ID lookup on a KeyRing.

    def sign(self, *messages):
        """
        Signs a message and returns a signature with the keccak hash.

        :param Iterable message: Message to sign in an iterable of bytes

        :rtype: bytestring
        :return: Signature of message
        """
        try:
            sig_keypair = self._power_ups[SigningKeypair]
        except KeyError:
            raise NoSigningPower
        msg_digest = sig_keypair.digest(*messages)
        return sig_keypair.sign(msg_digest)

    def encrypt_for(self, pubkey_sign_id, cleartext):
        try:
            enc_keypair = self._power_ups[EncryptingKeypair]
        except KeyError:
            raise NoSigningPower


class PowerUp(object):
    """
    Gives you MORE CryptoPower!
    """


class SigningKeypair(PowerUp):

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

    def _vrs_msgpack_dump(self, v, r, s):
        v_bytes = v.to_bytes(1, byteorder='big')
        r_bytes = r.to_bytes(32, byteorder='big')
        s_bytes = s.to_bytes(32, byteorder='big')
        return msgpack.dumps((v_bytes, r_bytes, s_bytes))

    def _vrs_msgpack_load(self, msgpack_vrs):
        sig = msgpack.loads(msgpack_vrs)
        v = int.from_bytes(sig[0], byteorder='big')
        r = int.from_bytes(sig[1], byteorder='big')
        s = int.from_bytes(sig[2], byteorder='big')
        return (v, r, s)

    def digest(self, *messages):
        """
        Accepts an iterable containing bytes and digests it.

        :param bytes *args: Data to hash

        :rtype: bytes
        :return: bytestring of digested data
        """
        hash = sha3.keccak_256()
        for message in messages:
            hash.update(message)
        return hash.digest()

    def sign(self, msghash):
        """
        Signs a hashed message and returns a msgpack'ed v, r, and s.

        :param bytes msghash: Hash of the message

        :rtype: Bytestring
        :return: Msgpacked bytestring of v, r, and s (the signature)
        """
        v, r, s = ecdsa_raw_sign(msghash, self.priv_key)
        return self._vrs_msgpack_dump(v, r, s)

    def verify(self, msghash, signature, pubkey=None):
        """
        Takes a msgpacked signature and verifies the message.

        :param bytes msghash: The hashed message to verify
        :param bytes signature: The msgpacked signature (v, r, and s)
        :param bytes pubkey: Pubkey to validate signature for
                             Default is the keypair's pub_key.

        :rtype: Boolean
        :return: Is the signature valid or not?
        """
        if not pubkey:
            pubkey = self.pub_key
        sig = self._vrs_msgpack_load(signature)
        # Generate the public key from the signature and validate
        # TODO: Look into fixed processing time functions for comparison
        verify_sig = ecdsa_raw_recover(msghash, sig)
        return verify_sig == pubkey

    def public_key(self):
        return self.pub_key
