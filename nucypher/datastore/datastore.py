"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from datetime import datetime
from typing import List

import maya
from bytestring_splitter import BytestringSplitter
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag

from nucypher.crypto.signing import Signature
from nucypher.crypto.utils import fingerprint_from_key
from nucypher.datastore.db.models import Key, PolicyArrangement, Workorder


class NotFound(Exception):
    """
    Exception class for Datastore calls for objects that don't exist.
    """
    pass


class Datastore:
    """
    A storage class of persistent cryptographic entities for use by Ursula.
    """
    kfrag_splitter = BytestringSplitter(Signature, (KFrag, KFrag.expected_bytes_length()))

    def __init__(self, sqlalchemy_engine=None) -> None:
        """
        Initializes a Datastore object.

        :param sqlalchemy_engine: SQLAlchemy engine object to create session
        """
        self.engine = sqlalchemy_engine
        Session = sessionmaker(bind=sqlalchemy_engine)

        # This will probably be on the reactor thread for most production configs.
        # Best to treat like hot lava.
        self._session_on_init_thread = Session()

    @staticmethod
    def __commit(session) -> None:
        try:
            session.commit()
        except OperationalError:
            session.rollback()
            raise

    #
    # Keys
    #

    def add_key(self,
                key: UmbralPublicKey,
                is_signing: bool = True,
                session=None
                ) -> Key:
        """
        :param key: Keypair object to store in the keystore.

        :return: The newly added key object.
        """
        session = session or self._session_on_init_thread
        fingerprint = fingerprint_from_key(key)
        key_data = bytes(key)
        new_key = Key(fingerprint, key_data, is_signing)

        session.add(new_key)
        self.__commit(session=session)
        return new_key

    def get_key(self, fingerprint: bytes, session=None) -> UmbralPublicKey:
        """
        Returns a key from the Datastore.

        :param fingerprint: Fingerprint, in bytes, of key to return

        :return: Keypair of the returned key.
        """
        session = session or self._session_on_init_thread

        key = session.query(Key).filter_by(fingerprint=fingerprint).first()
        if not key:
            raise NotFound("No key with fingerprint {} found.".format(fingerprint))

        pubkey = UmbralPublicKey.from_bytes(key.key_data)
        return pubkey

    def del_key(self, fingerprint: bytes, session=None):
        """
        Deletes a key from the Datastore.

        :param fingerprint: Fingerprint of key to delete
        """
        session = session or self._session_on_init_thread

        session.query(Key).filter_by(fingerprint=fingerprint).delete()
        self.__commit(session=session)

    #
    # Arrangements
    #

    def add_policy_arrangement(self,
                               expiration: maya.MayaDT,
                               arrangement_id: bytes,
                               kfrag: KFrag = None,
                               alice_verifying_key: UmbralPublicKey = None,
                               alice_signature: Signature = None,  # TODO: Why is this unused?
                               session=None
                               ) -> PolicyArrangement:
        """
        Creates a PolicyArrangement to the Keystore.

        :return: The newly added PolicyArrangement object
        """
        session = session or self._session_on_init_thread

        alice_key_instance = session.query(Key).filter_by(key_data=bytes(alice_verifying_key)).first()
        if not alice_key_instance:
            alice_key_instance = Key.from_umbral_key(alice_verifying_key, is_signing=True)

        new_policy_arrangement = PolicyArrangement(
            expiration=expiration,
            id=arrangement_id,
            kfrag=kfrag,
            alice_verifying_key=alice_key_instance,
            alice_signature=None,
            # bob_verifying_key.id  # TODO: Is this needed?
        )

        session.add(new_policy_arrangement)
        self.__commit(session=session)
        return new_policy_arrangement

    def get_policy_arrangement(self, arrangement_id: bytes, session=None) -> PolicyArrangement:
        """
        Retrieves a PolicyArrangement by its HRAC.

        :return: The PolicyArrangement object
        """
        session = session or self._session_on_init_thread
        policy_arrangement = session.query(PolicyArrangement).filter_by(id=arrangement_id).first()
        if not policy_arrangement:
            raise NotFound("No PolicyArrangement {} found.".format(arrangement_id))
        return policy_arrangement

    def get_all_policy_arrangements(self, session=None) -> List[PolicyArrangement]:
        """
        Returns all the PolicyArrangements

        :return: The list of PolicyArrangement objects
        """
        session = session or self._session_on_init_thread
        arrangements = session.query(PolicyArrangement).all()
        return arrangements

    def attach_kfrag_to_saved_arrangement(self, alice, id_as_hex, kfrag, session=None):
        session = session or self._session_on_init_thread
        policy_arrangement = session.query(PolicyArrangement).filter_by(id=id_as_hex.encode()).first()

        if policy_arrangement is None:
            raise NotFound("Can't attach a kfrag to non-existent Arrangement {}".format(id_as_hex))

        if policy_arrangement.alice_verifying_key.key_data != alice.stamp:
            raise alice.SuspiciousActivity

        policy_arrangement.kfrag = bytes(kfrag)
        self.__commit(session=session)

    def del_policy_arrangement(self, arrangement_id: bytes, session=None) -> int:
        """
        Deletes a PolicyArrangement from the Keystore.
        """
        session = session or self._session_on_init_thread
        deleted_records = session.query(PolicyArrangement).filter_by(id=arrangement_id).delete()

        self.__commit(session=session)
        return deleted_records

    def del_expired_policy_arrangements(self, session=None, now=None) -> int:
        """
        Deletes all expired PolicyArrangements from the Keystore.
        """
        session = session or self._session_on_init_thread
        now = now or datetime.now()
        result = session.query(PolicyArrangement).filter(PolicyArrangement.expiration <= now)

        deleted_records = 0
        if result.count() > 0:
            deleted_records = result.delete()
        self.__commit(session=session)
        return deleted_records

    #
    # Work Orders
    #

    def save_workorder(self,
                       bob_verifying_key: UmbralPublicKey,
                       bob_signature: Signature,
                       arrangement_id: bytes,
                       session=None
                       ) -> Workorder:
        """
        Adds a Workorder to the keystore.
        """
        session = session or self._session_on_init_thread

        # Get or Create Bob Verifying Key
        fingerprint = fingerprint_from_key(bob_verifying_key)
        key = session.query(Key).filter_by(fingerprint=fingerprint).first()
        if not key:
            key = self.add_key(key=bob_verifying_key)

        new_workorder = Workorder(bob_verifying_key_id=key.id,
                                  bob_signature=bob_signature,
                                  arrangement_id=arrangement_id)

        session.add(new_workorder)
        self.__commit(session=session)
        return new_workorder

    def get_workorders(self,
                       arrangement_id: bytes = None,
                       bob_verifying_key: bytes = None,
                       session=None
                       ) -> List[Workorder]:
        """
        Returns a list of Workorders by HRAC.
        """
        session = session or self._session_on_init_thread
        query = session.query(Workorder)

        if not arrangement_id and not bob_verifying_key:
            workorders = query.all()  # Return all records

        else:

            # Return arrangement records
            if arrangement_id:
                workorders = query.filter_by(arrangement_id=arrangement_id)

            # Return records for Bob
            else:
                fingerprint = fingerprint_from_key(bob_verifying_key)
                key = session.query(Key).filter_by(fingerprint=fingerprint).first()
                workorders = query.filter_by(bob_verifying_key_id=key.id)

            if not workorders:
                raise NotFound

        return list(workorders)

    def del_workorders(self, arrangement_id: bytes, session=None) -> int:
        """
        Deletes a Workorder from the Keystore.
        """
        session = session or self._session_on_init_thread

        workorders = session.query(Workorder).filter_by(arrangement_id=arrangement_id)
        deleted = workorders.delete()
        self.__commit(session=session)
        return deleted
