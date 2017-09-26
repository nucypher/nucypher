import msgpack
from random import SystemRandom
from py_ecc.secp256k1 import N, privtopub, ecdsa_raw_sign, ecdsa_raw_recover
from npre import umbral


class EncryptingKeypair(object):
    KEYSIZE = 32

    def __init__(self, privkey_bytes=None):
        self.pre = umbral.PRE()

        if not privkey_bytes:
            self.priv_key = self.pre.gen_priv(dtype='bytes')
        else:
            self.priv_key = privkey_bytes
        self.pub_key = self.pre.priv2pub(self.priv_key)

    def generate_key(self):
        """
        Generate a raw symmetric key and its encrypted counterpart.

        :rtype: Tuple(bytes, bytes)
        :return: Tuple of the raw encrypted key and the encrypted key
        """
        symm_key, enc_symm_key = self.pre.encapsulate(self.pub_key)
        return (symm_key, enc_symm_key)

    def decrypt_key(self, enc_key):
        """
        Decrypts an ECIES encrypted symmetric key.

        :rtype: bytes
        :return: Bytestring of the decrypted symmetric key
        """
        return self.pre.decapsulate(self.priv_key, enc_key)

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


class SigningKeypair(object):
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
