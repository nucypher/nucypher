import sha3
import npre.elliptic_curve as ec
from nacl.utils import random
from nacl.secret import SecretBox
from nkms.crypto.keypairs import SigningKeypair, EncryptingKeypair
from npre import umbral


class KeyRing(object):
    def __init__(self, sig_privkey=None, enc_privkey=None):
        """
        Initializes a KeyRing object. Uses the private keys to initialize
        their respective objects, if provided. If not, it will generate new
        keypairs.

        :param bytes sig_privkey: Private key in bytes of ECDSA signing keypair
        :param bytes enc_privkey: Private key in bytes of encrypting keypair
        """
        self.sig_keypair = SigningKeypair(sig_privkey)
        self.enc_keypair = EncryptingKeypair(enc_privkey)
        self.pre = umbral.PRE()

    @property
    def sig_pubkey(self):
        return self.sig_keypair.pub_key

    @property
    def sig_privkey(self):
        return self.sig_keypair.priv_key

    @property
    def enc_pubkey(self):
        return self.enc_keypair.pub_key

    @property
    def enc_privkey(self):
        return self.enc_keypair.priv_key

    def _split_path(self, path):
        """
        Splits the file path provided and provides subpaths to each directory.

        :param bytes path: Path to file

        :return: Subpath(s) from path
        :rtype: List of bytes
        """
        # Hacky workaround: b'/'.split(b'/') == b['', b'']
        if path == b'/':
            return [b'']

        dirs = path.split(b'/')
        return [b'/'.join(dirs[:i + 1]) for i in range(len(dirs))]

    def _derive_path_key(self, path, is_pub=True):
        """
        Derives a key for the specific path.

        :param bytes path: Path to generate the key for
        :param bool is_pub: Is the derived key a public key?

        :rtype: bytes
        :return: Derived key
        """
        key = sha3.keccak_256(self.enc_privkey + path).digest()
        return self.pre.priv2pub(key) if is_pub else key

    def sign(self, message):
        """
        Signs a message and returns a signature with the keccak hash.

        :param bytes message: Message to sign in bytes

        :rtype: bytestring
        :return: Signature of message
        """
        msg_digest = sha3.keccak_256(message).digest()
        return self.sig_keypair.sign(msg_digest)

    def verify(self, message, signature, pubkey=None):
        """
        Verifies a signature.

        :param bytes message: Message to check signature for
        :param bytes signature: Signature to validate
        :param bytes pubkey: Pubkey to validate signature with
                             Default is the sig_keypair's pub_key

        :rtype: Boolean
        :return: Is the message signature valid or not?
        """
        if not pubkey:
            pubkey = self.sig_keypair.pub_key
        msg_digest = sha3.keccak_256(message).digest()
        return self.sig_keypair.verify(msg_digest, signature, pubkey=pubkey)

    def generate_key(self):
        """
        Generates a raw symmetric key and its encrypted counterpart.

        :rtype: Tuple(bytes, EncryptedKey)
        :return: Tuple containing raw encrypted key and the encrypted key
        """
        symm_key, enc_symm_key = self.enc_keypair.generate_key()
        return (symm_key, enc_symm_key)

    def decrypt_key(self, enc_key, privkey=None):
        """
        Decrypts an ECIES encrypted symmetric key.

        :param EncryptedKey enc_key: ECIES encrypted key in bytes
        :param bytes privkey: The privkey to decrypt with

        :rtype: bytes
        :return: Bytestring of the decrypted symmetric key
        """
        return self.enc_keypair.decrypt_key(enc_key, privkey)

    def rekey(self, privkey_a, pubkey_b):
        """
        Generates a re-encryption key in interactive mode.

        :param bytes privkey_a: Alive's private key
        :param bytes pubkey_b: Bob's public key

        :rtype: bytes
        :return: Bytestring of a re-encryption key
        """
        # Generate an ephemeral keypair
        priv_e = self.enc_keypair.pre.gen_priv()
        priv_e_bytes = ec.serialize(priv_e)[1:]

        # Encrypt ephemeral key with an ECIES generated key
        symm_key_bob, enc_symm_key_bob = self.enc_keypair.generate_key(
                                                            pubkey=pubkey_b)
        enc_priv_e = self.symm_encrypt(symm_key_bob, priv_e_bytes)

        reenc_key = self.enc_keypair.rekey(self.enc_privkey, priv_e)
        return (reenc_key, enc_symm_key_bob, enc_priv_e)

    def reencrypt(self, reenc_key, ciphertext):
        """
        Re-encrypts the provided ciphertext for the recipient of the generated
        re-encryption key provided.

        :param bytes reenc_key: The re-encryption key from the proxy to Bob
        :param bytes ciphertext: The ciphertext to re-encrypt to Bob

        :rtype: bytes
        :return: Re-encrypted ciphertext
        """
        return self.enc_keypair.reencrypt(reenc_key, ciphertext)

    def gen_split_rekey(self, privkey_a, privkey_b, min_shares, num_shares):
        """
        Generates secret shares that can be used to reconstruct data given
        `min_shares` have been acquired.

        :param bytes privkey_a: Alice's private key
        :param bytes privkey_b: Bob's private key (or an ephemeral privkey)
        :param int min_shares: Threshold shares needed to reconstruct secret
        :param int num_shares: Total number of shares to create

        :rtype: List(RekeyFrag)
        :return: List of `num_shares` RekeyFrags
        """
        return self.enc_keypair.split_rekey(privkey_a, privkey_b,
                                            min_shares, num_shares)

    def build_secret(self, shares):
        """
        Reconstructs a secret from the given shares.

        :param list shares: List of secret share fragments

        :rtype: EncryptedKey
        :return: EncrypedKey from `shares`
        """
        # TODO: What to do if not enough shares, or invalid?
        return self.enc_keypair.combine(shares)

    def symm_encrypt(self, key, plaintext):
        """
        Encrypts the plaintext using SecretBox symmetric encryption.

        :param bytes key: Key to encrypt with
        :param bytes plaintext: Plaintext to encrypt

        :rtype: bytes
        :return: Ciphertext from SecretBox symmetric encryption
        """
        cipher = SecretBox(key)
        return cipher.encrypt(plaintext)

    def symm_decrypt(self, key, ciphertext):
        """
        Decrypts the ciphertext using SecretBox symmetric decryption.

        :param bytes key: Key to decrypt with
        :param bytes ciphertext: Ciphertext from SecretBox encryption

        :rtype: bytes
        :return: Plaintext from SecretBox decryption
        """
        cipher = SecretBox(key)
        return cipher.decrypt(ciphertext)

    def secure_random(self, length):
        """
        Generates a bytestring from a secure random source for keys, etc.

        :params int length: Length of the bytestring to generate.

        :rtype: bytes
        :return: Secure random generated bytestring of <length> bytes
        """
        return random(length)
