from typing import Union

from sqlalchemy.orm import sessionmaker

from nkms.crypto.constants import KFRAG_LENGTH
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.keystore.db.models import Key, PolicyContract, Workorder
from umbral.fragments import KFrag
from umbral.keys import UmbralPublicKey
from . import keypairs


class NotFound(Exception):
    """
    Exception class for KeyStore calls for objects that don't exist.
    """
    pass


class KeyStore(object):
    """
    A storage class of cryptographic keys.
    """
    kfrag_splitter = BytestringSplitter(Signature, (KFrag, KFRAG_LENGTH))

    def __init__(self, sqlalchemy_engine=None):
        """
        Initalizes a KeyStore object.

        :param sqlalchemy_engine: SQLAlchemy engine object to create session
        """
        self.session = sessionmaker(bind=sqlalchemy_engine)()

    def add_key(self, key, is_signing=True) -> Key:
        """
        :param key: Keypair object to store in the keystore.

        :return: The newly added key object.
        """
        fingerprint = key.get_fingerprint()
        key_data = key.serialize_pubkey()

        new_key = Key(fingerprint, key_data, is_signing)

        self.session.add(new_key)
        self.session.commit()
        return new_key


    def get_key(self, fingerprint: bytes) -> Union[keypairs.EncryptingKeypair,
                                                   keypairs.SigningKeypair]:
        """
        Returns a key from the KeyStore.

        :param fingerprint: Fingerprint, in bytes, of key to return

        :return: Keypair of the returned key.
        """
        key = self.session.query(Key).filter_by(fingerprint=fingerprint).first()
        if not key:
            raise NotFound(
                "No key with fingerprint {} found.".format(fingerprint))

        pubkey = UmbralPublicKey.from_bytes(key.key_data, as_b64=False)
        if key.is_signing:
            return keypairs.SigningKeypair(pubkey)
        else:
            return keypairs.EncryptingKeypair(pubkey)


    def del_key(self, fingerprint: bytes):
        """
        Deletes a key from the KeyStore.

        :param fingerprint: Fingerprint of key to delete
        """
        self.session.query(Key).filter_by(fingerprint=fingerprint).delete()
        self.session.commit()

    def add_policy_contract(self, expiration, deposit, hrac, kfrag=None,
                            alice_pubkey_sig=None, # alice_pubkey_enc,
                            alice_signature=None) -> PolicyContract:
        """
        Creates a PolicyContract to the Keystore.

        :return: The newly added PolicyContract object
        """
        # TODO: This can be optimized to one commit/write.
        alice_pubkey_sig = self.add_key(alice_pubkey_sig, is_signing=True)
        # alice_pubkey_enc = self.add_key(alice_pubkey_enc)
        # bob_pubkey_sig = self.add_key(bob_pubkey_sig)

        new_policy_contract = PolicyContract(
            expiration, deposit, hrac, kfrag, alice_pubkey_sig=alice_pubkey_sig,
            alice_signature=None, # bob_pubkey_sig.id
        )

        self.session.add(new_policy_contract)
        self.session.commit()

        return new_policy_contract

    def get_policy_contract(self, hrac: bytes) -> PolicyContract:
        """
        Returns the PolicyContract by its HRAC.

        :return: The PolicyContract object
        """
        policy_contract = self.session.query(PolicyContract).filter_by(hrac=hrac).first()
        if not policy_contract:
            raise NotFound("No PolicyContract with {} HRAC found.".format(hrac))
        return policy_contract

    def del_policy_contract(self, hrac: bytes):
        """
        Deletes a PolicyContract from the Keystore.
        """
        self.session.query(PolicyContract).filter_by(hrac=hrac).delete()
        self.session.commit()

    def add_workorder(self, bob_pubkey_sig, bob_signature, hrac) -> Workorder:
        """
        Adds a Workorder to the keystore.
        """
        bob_pubkey_sig = self.add_key(bob_pubkey_sig)
        new_workorder = Workorder(bob_pubkey_sig.id, bob_signature, hrac)

        self.session.add(new_workorder)
        self.session.commit()
        return new_workorder

    def get_workorders(self, hrac: bytes) -> Workorder:
        """
        Returns a list of Workorders by HRAC.
        """
        workorders = self.session.query(Workorder).filter_by(hrac=hrac)
        if not workorders:
            raise NotFound("No Workorders with {} HRAC found.".format(hrac))
        return workorders

    def del_workorders(self, hrac: bytes):
        """
        Deletes a Workorder from the Keystore.
        """
        workorders = self.session.query(Workorder).filter_by(hrac=hrac).delete()
        self.session.commit()
