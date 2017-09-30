from npre import umbral
from npre import elliptic_curve as ec
from nacl.secret import SecretBox
from typing import Tuple
from threading import local

_tl = local()
_tl.pre = None


class EncryptingKeypair(object):
    KEYSIZE = 32

    def __init__(self, privkey: bytes = None):
        """
        :privkey: Optional private key in a serialized form (32-byte string)
                  If not given, a random one is generated.
        """
        # Creating PRE object is slow
        # so let's reuse it per-thread
        if not _tl.pre:
            _tl.pre = umbral.PRE()
        self.pre = _tl.pre

        if not privkey:
            self._priv_key = self.pre.gen_priv()
        else:
            self._priv_key = ec.deserialize(
                    self.pre.ecgroup, b'\x00' + privkey)

        # We don't always need a public key, so let's make it lazily
        self.__pub_key = None

    @property
    def _pub_key(self):
        """
        Lazy generation of a public key
        """
        if self.__pub_key is None:
            self.__pub_key = self.pre.priv2pub(self._priv_key)
        return self.__pub_key

    @property
    def pub_key(self):
        return ec.serialize(self._pub_key)

    def encrypt(self,
                data: bytes,
                pubkey: bytes = None) -> Tuple[bytes, bytes]:
        """
        :data:      The data to encrypt. If derived per-subpath, it's a
                    symmetric key to use for block ciphers.
        :pubkey:    Optional public key to encrypt for. If not given, encrypt
                    for ours

        :returns:   (ekey, edata) where ekey is needed for recepient to
                    reconstruct a DH secret, edata is data encrypted with this
                    DH secret. The output should be treated as a monolithic
                    ciphertext outside of this class
        """
        if pubkey is None:
            pubkey = self._pub_key
        else:
            pubkey = ec.deserialize(self.pre.ecgroup, pubkey)

        key, ekey = self.pre.encapsulate(pubkey)
        cipher = SecretBox(key)

        return (ec.serialize(ekey.ekey),
                cipher.encrypt(data))

    def decrypt(self,
                edata: Tuple[bytes, bytes]) -> bytes:
        """
        Decrypt data encrypted by ECIES
        edata = (ekey, edata)
            ekey is needed to reconstruct a DH secret
            edata encrypted by the block cipher
        """
        ekey, edata = edata
        ekey = umbral.EncryptedKey(
                ekey=ec.deserialize(self.pre.ecgroup, ekey), re_id=None)
        key = self.pre.decapsulate(self._priv_key, ekey)
        cipher = SecretBox(key)
        return cipher.decrypt(edata)

    def rekey(self,
              pubkey: bytes) -> Tuple[bytes, Tuple[bytes, bytes]]:
        """
        Create re-encryption key from private key which we have to public key
        pubkey.
        Internally, we create an ephemeral key priv_eph randomly and share data
        with it, and also attach encrypted priv_eph as the second part of the
        tuple
        """
        priv_eph = self.pre.gen_priv()
        rk = self.pre.rekey(self._priv_key, priv_eph)
        encrypted_eph = self.encrypt(ec.serialize(priv_eph))
        return (ec.serialize(rk), encrypted_eph)

    def reencrypt():
        pass

    def combine():
        pass

    def split_rekey():
        pass
