import sha3
from nkms.keystore import keypairs, constants
from nkms.keystore.db.models import Key, KeyFrag
from nkms.crypto.utils import BytestringSplitter
from nkms.crypto.signature import Signature
from sqlalchemy.orm import sessionmaker
from typing import Union
from npre.umbral import RekeyFrag


class KeyNotFound(KeyError):
    """
    Exception class for KeyStore get_key calls for keys that don't exist.
    """
    pass


class KeyStore(object):
    """
    A storage class of cryptographic keys.
    """

    kFrag_splitter = BytestringSplitter(
            Signature,
            (bytes, constants.REKEY_FRAG_ID_LEN),
            (bytes, constants.REKEY_FRAG_KEY_LEN)
    )

    def __init__(self, sqlalchemy_engine=None):
        """
        Initalizes a KeyStore object.

        :param sqlalchemy_engine: SQLAlchemy engine object to create session
        """
        self.session = sessionmaker(bind=sqlalchemy_engine)()

    def _get_fingerprint(self, key: bytes) -> bytes:
        """
        Hashes the key using keccak_256 and returns the hexdigest in bytes.

        :param key: Key to hash

        :return: Hexdigest fingerprint of key (keccak 256) in bytes
        """
        return sha3.keccak_256(key).hexdigest().encode()

    def generate_encrypting_keypair(self, gen_priv=True) -> keypairs.EncryptingKeypair:
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

    def generate_signing_keypair(self, gen_priv=True) -> keypairs.SigningKeypair:
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
        key = self.session.query(Key).filter_by(fingerprint=fingerprint).first()
        if not key:
            raise KeyNotFound(
                    "No key with fingerprint {} found.".format(fingerprint))
        return keypairs.Keypair.deserialize_key(key.key_data)

    def get_kfrag(self, hrac: bytes, get_sig: bool=False) -> RekeyFrag:
        """
        Returns a RekeyFrag from the KeyStore.

        :param hrac: HRAC in bytes

        :return: Deserialized RekeyFrag from KeyStore
        """
        kfrag = self.session.query(KeyFrag).filter_by(hrac=hrac).first()
        if not kfrag:
            raise KeyNotFound(
                "No KeyFrag with HRAC {} found."
                .format(hrac)
            )
        # TODO: Make this use a class
        sig, id, key = self.kFrag_splitter(kfrag.key_frag)

        kFrag = RekeyFrag(id=id, key=key)
        if get_sig:
            return (kFrag, sig)
        return kFrag

    def add_key(self,
                keypair: Union[keypairs.EncryptingKeypair,
                               keypairs.SigningKeypair],
                store_pub: bool = True) -> bytes:
        """
        Gets a fingerprint of the key and adds it to the keystore.

        :param key: Key, in bytes, to add to lmdb

        :return: Fingerprint, in bytes, of the added key
        """
        if store_pub:
            fingerprint = self._get_fingerprint(keypair.pubkey)
            key = keypair.serialize_pubkey()
        else:
            fingerprint = self._get_fingerprint(keypair.privkey)
            key = keypair.serialize_privkey()

        # Create new Key object and commit to db
        self.session.add(Key(key))
        self.session.commit()
        return fingerprint

    def add_kfrag(self, hrac: bytes, kfrag: RekeyFrag, sig: bytes=None):
        """
        Adds a RekeyFrag to sqlite.

        :param hrac: Hashed Resource Authenticate Code
        :param kfrag: RekeyFrag instance to add to sqlite
        :param sig: Signature of kfrag (if exists)
        """
        kfrag_data = b''
        if sig:
            kfrag_data += sig
        kfrag_data += bytes(kfrag)

        kfrag = KeyFrag(hrac, kfrag_data)
        self.session.add(kfrag)
        self.session.commit()

    def del_key(self, fingerprint: bytes):
        """
        Deletes a key from the KeyStore.

        :param fingerprint: Fingerprint of key to delete
        """
        self.session.query(Key).filter_by(fingerprint=fingerprint).delete()
        self.session.commit()

    def del_kfrag(self, hrac: bytes):
        """
        Deletes a RekeyFrag from sqlite.

        :param hrac: Hashed Resource Authentication Code
        """
        self.session.query(KeyFrag).filter_by(hrac=hrac).delete()
        self.session.commit()
