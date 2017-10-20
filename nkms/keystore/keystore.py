import lmdb
import sha3
from nkms.keystore import keypairs
from nkms.keystore import constants
from typing import Union


class KeyStore(object):
    """
    A storage class of cryptographic keys.
    """

    def __init__(self, lmdb_path):
        """
        Initalizes a KeyStore object.

        :param lmdb_path: LMDB path to open for reading
        """
        self.lmdb_env = lmdb.open(lmdb_path)

    def __del__(self):
        """
        KeyStore cleanup?
        """
        self.lmdb_env.close()

    def _get_fingerprint(self, key: bytes) -> bytes:
        """
        Hashes the key using keccak_256 and returns the hexdigest in bytes.

        :param key: Key to hash

        :return: Hexdigest fingerprint of key (keccak 256) in bytes
        """
        return sha3.keccak_256(key).hexdigest().encode()

    def gen_ecies_keypair(self, gen_priv=True) -> keypairs.EncryptingKeypair:
        """
        Generates an ECIES keypair.

        TODO: Initalize keypair with provided data.

        :param gen_priv: Generate private key or not?

        :return: ECIES encrypting keypair
        """
        ecies_keypair = keypairs.EncryptingKeypair()
        if gen_priv:
            ecies_keypair.gen_privkey()
        return ecies_keypair

    def gen_ecdsa_keypair(self, gen_priv=True) -> keypairs.SigningKeypair:
        """
        Generates an ECDSA keypair.

        TODO: Initalize keypair with provided data.

        :param gen_priv: Generate private key or not?

        :return ECDSA signing keypair
        """
        ecdsa_keypair = keypairs.SigningKeypair()
        if gen_priv:
            ecdsa_keypair.gen_privkey()
        return ecdsa_keypair

    def get_key(self, fingerprint: bytes) -> Union[keypairs.EncryptingKeypair,
                                                   keypairs.SigningKeypair]:
        """
        Returns a key from the KeyStore.

        :param fingerprint: Fingerprint, in bytes, of key to return

        :return: Keypair of the returned key.

        """
        with self.lmdb_env.begin() as txn:
            key = txn.get(fingerprint)

        keypair_byte = key[0]
        key_type_byte = key[1]
        key = key[2:]

        if keypair_byte == constants.ENC_KEYPAIR_BYTE:
            if key_type_byte == constants.PUB_KEY_BYTE:
                return keypairs.EncryptingKeypair(pubkey=key)

            elif key_type_byte == constants.PRIV_KEY_BYTE:
                return keypairs.EncryptingKeypair(privkey=key)

        elif keypair_byte == constants.SIG_KEYPAIR_BYTE:
            if key_type_byte == constants.PUB_KEY_BYTE:
                return keypairs.SigningKeypair(pubkey=key)

            elif key_type_byte == constants.PRIV_KEY_BYTE:
                return keypairs.SigningKeypair(privkey=key)

    def add_key(self,
                keypair: Union[keypairs.EncryptingKeypair,
                               keypairs.SigningKeypair],
                store_pub: bool = True) -> bytes:
        """
        Gets a fingerprint of the key and adds it to the keystore.

        :param key: Key, in bytes, to add to lmdb
        ::

        :return: Fingerprint, in bytes, of the added key
        """
        if store_pub:
            fingerprint = self._get_fingerprint(keypair.pubkey)
            key = keypair.serialize_pubkey()
        else:
            fingerprint = self._get_fingerprint(keypair.privkey)
            key = keypair.serialize_privkey()

        with self.lmdb_env.begin(write=True) as txn:
            txn.put(fingerprint, key)
        return fingerprint

    def del_key(self):
        """
        Deletes a key from the KeyStore.

        TODO: Implement this.
        TODO: Delete key by KeyID.
        """
        pass
