from typing import Union

from nkms.crypto.constants import KFRAG_LENGTH
from nkms.crypto.signature import Signature
from bytestring_splitter import BytestringSplitter
from nkms.keystore.db.models import Key, PolicyArrangement, Workorder
from umbral.fragments import KFrag
from umbral.keys import UmbralPublicKey
from . import keypairs
from nkms.crypto.utils import fingerprint_from_key
from sqlalchemy.orm import sessionmaker


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
        self.engine = sqlalchemy_engine
        Session = sessionmaker(bind=sqlalchemy_engine)

        # This will probably be on the reactor thread for most production configs.
        # Best to treat like hot lava.
        self._session_on_init_thread = Session()

    def add_key(self, key, is_signing=True, session=None) -> Key:
        """
        :param key: Keypair object to store in the keystore.

        :return: The newly added key object.
        """
        session = session or self._session_on_init_thread
        fingerprint = fingerprint_from_key(key)
        key_data = bytes(key)
        new_key = Key(fingerprint, key_data, is_signing)

        session.add(new_key)
        session.commit()

        return new_key

    def get_key(self, fingerprint: bytes, session=None) -> Union[keypairs.EncryptingKeypair,
                                                   keypairs.SigningKeypair]:
        """
        Returns a key from the KeyStore.

        :param fingerprint: Fingerprint, in bytes, of key to return

        :return: Keypair of the returned key.
        """
        session = session or self._session_on_init_thread

        key = session.query(Key).filter_by(fingerprint=fingerprint).first()

        if not key:
            raise NotFound(
                "No key with fingerprint {} found.".format(fingerprint))

        pubkey = UmbralPublicKey.from_bytes(key.key_data)
        return pubkey

    def del_key(self, fingerprint: bytes, session=None):
        """
        Deletes a key from the KeyStore.

        :param fingerprint: Fingerprint of key to delete
        """
        session = session or self._session_on_init_thread

        session.query(Key).filter_by(fingerprint=fingerprint).delete()
        session.commit()

    def add_policy_arrangement(self, expiration, deposit, hrac, kfrag=None,
                               alice_pubkey_sig=None, # alice_pubkey_enc,
                               alice_signature=None, session=None) -> PolicyArrangement:
        """
        Creates a PolicyArrangement to the Keystore.

        :return: The newly added PolicyArrangement object
        """
        session = session or self._session_on_init_thread

        alice_key_instance = session.query(Key).filter_by(key_data=bytes(alice_pubkey_sig)).first()
        if not alice_key_instance:
            alice_key_instance = Key.from_umbral_key(alice_pubkey_sig, is_signing=True)
        # alice_pubkey_enc = self.add_key(alice_pubkey_enc)
        # bob_pubkey_sig = self.add_key(bob_pubkey_sig)

        new_policy_arrangement = PolicyArrangement(
            expiration, deposit, hrac, kfrag, alice_pubkey_sig=alice_key_instance,
            alice_signature=None, # bob_pubkey_sig.id
        )

        session.add(new_policy_arrangement)
        session.commit()

        return new_policy_arrangement

    def get_policy_arrangement(self, hrac: bytes, session=None) -> PolicyArrangement:
        """
        Returns the PolicyArrangement by its HRAC.

        :return: The PolicyArrangement object
        """
        session = session or self._session_on_init_thread

        policy_arrangement = session.query(PolicyArrangement).filter_by(hrac=hrac).first()

        if not policy_arrangement:
            raise NotFound("No PolicyArrangement with {} HRAC found.".format(hrac))
        return policy_arrangement

    def del_policy_arrangement(self, hrac: bytes, session=None):
        """
        Deletes a PolicyArrangement from the Keystore.
        """
        session = session or self._session_on_init_thread

        session.query(PolicyArrangement).filter_by(hrac=hrac).delete()
        session.commit()

    def attach_kfrag_to_saved_arrangement(self, alice, hrac_as_hex, kfrag, session=None):
        session = session or self._session_on_init_thread
        
        policy_arrangement = session.query(PolicyArrangement).filter_by(hrac=hrac_as_hex.encode()).first()

        if policy_arrangement is None:
            raise NotFound("Can't attach a kfrag to non-existent Arrangement with hrac {}".format(hrac_as_hex))

        if policy_arrangement.alice_pubkey_sig.key_data != alice.stamp:
            raise alice.SuspiciousActivity

        policy_arrangement.k_frag = bytes(kfrag)
        session.commit()

    def add_workorder(self, bob_pubkey_sig, bob_signature, hrac, session=None) -> Workorder:
        """
        Adds a Workorder to the keystore.
        """
        session = session or self._session_on_init_thread
        bob_pubkey_sig = self.add_key(bob_pubkey_sig)
        new_workorder = Workorder(bob_pubkey_sig.id, bob_signature, hrac)

        session.add(new_workorder)
        session.commit()

        return new_workorder

    def get_workorders(self, hrac: bytes, session=None) -> Workorder:
        """
        Returns a list of Workorders by HRAC.
        """
        session = session or self._session_on_init_thread

        workorders = session.query(Workorder).filter_by(hrac=hrac)

        if not workorders:
            raise NotFound("No Workorders with {} HRAC found.".format(hrac))
        return workorders

    def del_workorders(self, hrac: bytes, session=None):
        """
        Deletes a Workorder from the Keystore.
        """
        session = session or self._session_on_init_thread

        workorders = session.query(Workorder).filter_by(hrac=hrac)
        deleted = workorders.delete()
        session.commit()

        return deleted
