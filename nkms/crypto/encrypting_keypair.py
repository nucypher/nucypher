from npre import umbral
from npre import elliptic_curve as ec
from nacl.secret import SecretBox
from typing import Tuple, List
from threading import local

from nkms.crypto.api import PRE

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

        return ((ec.serialize(ekey.ekey), None),
                cipher.encrypt(data))

    def decrypt(self,
                edata: Tuple[bytes, bytes],
                privkey: bytes = None) -> bytes:
        """
        Decrypt data encrypted by ECIES
        edata = (ekey, edata)
            ekey is needed to reconstruct a DH secret
            edata encrypted by the block cipher
            privkey is optional private key if we want to use something else
            than what keypair uses
        """
        if isinstance(edata[0], tuple) and isinstance(edata[1], tuple):
            # In case it was re-encrypted data
            return self.decrypt_reencrypted(edata)

        ekey, edata = edata
        # When it comes to decrypt(), ekey[1] is always None
        # we could use that and save 2 bytes,
        # but it makes the code less readable
        ekey = umbral.EncryptedKey(
                ekey=ec.deserialize(self.pre.ecgroup, ekey[0]), re_id=ekey[1])
        if privkey is None:
            privkey = self._priv_key
        else:
            privkey = ec.deserialize(self.pre.ecgroup, privkey)

        key = self.pre.decapsulate(privkey, ekey)
        cipher = SecretBox(key)
        return cipher.decrypt(edata)

    def decrypt_reencrypted(
            self,
            edata: Tuple[Tuple[bytes, bytes], Tuple[bytes, bytes]]
            ) -> bytes:
        """
        Decrypt data which was re-encrypted for our public key
        Format of edata is the same as the output of reencrypt() method:
        data encrypted with an ephemeral key
        and the ephemeral private key encrypted for recepient (Bob)
        """
        edata_by_eph, encrypted_eph = edata
        priv_eph = self.decrypt(encrypted_eph)
        return self.decrypt(edata_by_eph, privkey=priv_eph)

    def rekey(self,
              pubkey: bytes) -> Tuple[tuple, Tuple[bytes, bytes]]:
        """
        Create re-encryption key from private key which we have to public key
        pubkey.
        Internally, we create an ephemeral key priv_eph randomly and share data
        with it, and also attach encrypted priv_eph as the second part of the
        tuple
        """
        priv_eph = self.pre.gen_priv()
        rk = self.pre.rekey(self._priv_key, priv_eph)
        encrypted_eph = self.encrypt(ec.serialize(priv_eph), pubkey=pubkey)
        return ((rk.id, ec.serialize(rk.key)), encrypted_eph)

    def reencrypt(self,
                  rekey: Tuple[tuple, Tuple[bytes, bytes]],
                  ciphertext: Tuple[bytes, bytes]
                  ) -> Tuple[Tuple[bytes, bytes], Tuple[bytes, bytes]]:
        """
        Re-encrypt for public key
        rekey is (rk, encrypted_eph), same as output of rekey()
        ciphertext is a tuple in the same format as output of encrypt()

        Output is two tuples: data encrypted with an ephemeral key
        and the ephemeral private key encrypted for recepient (Bob)
        """
        rk, encrypted_eph = rekey
        rk = umbral.RekeyFrag(rk[0], ec.deserialize(self.pre.ecgroup, rk[1]), pre=PRE)
        ekey, edata = ciphertext
        ekey = umbral.EncryptedKey(
                ekey=ec.deserialize(self.pre.ecgroup, ekey[0]), re_id=ekey[1])

        ekey = self.pre.reencrypt(rk, ekey)

        ekey = (ec.serialize(ekey.ekey), ekey.re_id)
        return (ekey, edata), encrypted_eph

    def combine(self,
                shares: Tuple[Tuple[bytes, bytes], Tuple[bytes, bytes]]
                ) -> Tuple[Tuple[bytes, bytes], Tuple[bytes, bytes]]:
        ekeys = [umbral.EncryptedKey(
                    ekey=ec.deserialize(self.pre.ecgroup, share[0][0][0]),
                    re_id=share[0][0][1])
                 for share in shares]
        ekey = self.pre.combine(ekeys)
        ekey = (ec.serialize(ekey.ekey), ekey.re_id)

        # Everything except ekey is the same for all shares!
        # TODO instead of trusting the first share, trust the majority
        return (ekey, shares[0][0][1]), shares[0][1]

    def split_rekey(self,
                    pubkey: bytes,
                    min_shares: int,
                    num_shares: int
                    ) -> List[Tuple[tuple, Tuple[bytes, bytes]]]:
        priv_eph = self.pre.gen_priv()
        rks = self.pre.split_rekey(self._priv_key, priv_eph,
                                   min_shares, num_shares)
        encrypted_eph = self.encrypt(ec.serialize(priv_eph), pubkey=pubkey)

        return [((rk.id, ec.serialize(rk.key)), encrypted_eph)
                for rk in rks]
