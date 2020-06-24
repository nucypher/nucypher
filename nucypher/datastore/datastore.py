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
import lmdb
import maya
from contextlib import contextmanager, suppress
from bytestring_splitter import BytestringSplitter
from typing import Union

from nucypher.crypto.signing import Signature
from nucypher.datastore.base import DatastoreRecord, RecordField
from nucypher.datastore.models import PolicyArrangement, Workorder


class RecordNotFound(Exception):
    """
    Exception class for Datastore calls for objects that don't exist.
    """
    pass


class DatastoreTransactionError(Exception):
    """
    Exception class for errors during transactions in the datastore.
    """
    pass


class Datastore:
    """
    A persistent storage layer for arbitrary data for use by NuCypher characters.
    """

    # LMDB has a `map_size` arg that caps the total size of the database.
    # We can set this arbitrarily high (1TB) to prevent any run-time crashes.
    LMDB_MAP_SIZE = 1_000_000_000_000

    def __init__(self, db_path: str) -> None:
        """
        Initializes a Datastore object by path.

        :param db_path: Filepath to a lmdb database.
        """
        self.db_path = db_path
        self.__db_env = lmdb.open(db_path, map_size=self.LMDB_MAP_SIZE)

    @contextmanager
    def describe(self, record_type: 'DatastoreRecord', record_id: Union[int, str], writeable: bool=False):
        """
        This method is used to perform CRUD operations on the datastore within
        the safety of a context manager by returning an instance of the
        `record_type` identified by the `record_id` provided.

        When `writeable` is `False`, the record returned by this method
        cannot be used for any operations that write to the datastore. If an
        attempt is made to retrieve a non-existent record whilst `writeable`
        is `False`, this method raises a `RecordNotFound` error.

        When `writeable` is `True`, the record can be used to perform writes
        on the datastore. In the event an error occurs during the write, the
        transaction will be aborted and no data will be written, and a
        `DatastoreTransactionError` will be raised.

        If the record is used outside the scope of the context manager, any
        writes or reads will error.
        """
        try:
            with self.__db_env.begin(write=writeable) as datastore_tx:
                record = record_type(datastore_tx, record_id, writeable=writeable)
                yield record
        except (AttributeError, TypeError) as tx_err:
            # Handle `RecordNotFound` cases when `writeable` is `False`.
            if not writeable and isinstance(tx_err, AttributeError):
                raise RecordNotFound(tx_err)
            raise DatastoreTransactionError(f'An error was encountered during the transaction (no data was written): {tx_err}')
        finally:
            # Set the `writeable` instance variable to `False` so that writes
            # cannot be attempted on the leftover reference. This isn't really
            # possible because the `datastore_tx` is no longer usable, but
            # we set this to ensure some degree of safety.
            record.__dict__['_DatastoreRecord__writeable'] = False

#class Datastore:
#    """
#    A storage class of persistent cryptographic entities for use by Ursula.
#    """
#    kfrag_splitter = BytestringSplitter(Signature, (KFrag, KFrag.expected_bytes_length()))
#
#    def __init__(self, sqlalchemy_engine=None) -> None:
#        """
#        Initializes a Datastore object.
#
#        :param sqlalchemy_engine: SQLAlchemy engine object to create session
#        """
#        self.engine = sqlalchemy_engine
#        Session = sessionmaker(bind=sqlalchemy_engine)
#
#        # This will probably be on the reactor thread for most production configs.
#        # Best to treat like hot lava.
#        self._session_on_init_thread = Session()
#
#    @staticmethod
#    def __commit(session) -> None:
#        try:
#            session.commit()
#        except OperationalError:
#            session.rollback()
#            raise
#
#    #
#    # Arrangements
#    #
#
#    def add_policy_arrangement(self,
#                               expiration: maya.MayaDT,
#                               arrangement_id: bytes,
#                               kfrag: KFrag = None,
#                               alice_verifying_key: UmbralPublicKey = None,
#                               alice_signature: Signature = None,  # TODO: Why is this unused?
#                               session=None
#                               ) -> PolicyArrangement:
#        """
#        Creates a PolicyArrangement to the Keystore.
#
#        :return: The newly added PolicyArrangement object
#        """
#        session = session or self._session_on_init_thread
#
#        new_policy_arrangement = PolicyArrangement(
#            expiration=expiration,
#            id=arrangement_id,
#            kfrag=kfrag,
#            alice_verifying_key=bytes(alice_verifying_key),
#            alice_signature=None,
#            # bob_verifying_key.id  # TODO: Is this needed?
#        )
#
#        session.add(new_policy_arrangement)
#        self.__commit(session=session)
#        return new_policy_arrangement
#
#    def get_policy_arrangement(self, arrangement_id: bytes, session=None) -> PolicyArrangement:
#        """
#        Retrieves a PolicyArrangement by its HRAC.
#
#        :return: The PolicyArrangement object
#        """
#        session = session or self._session_on_init_thread
#        policy_arrangement = session.query(PolicyArrangement).filter_by(id=arrangement_id).first()
#        if not policy_arrangement:
#            raise NotFound("No PolicyArrangement {} found.".format(arrangement_id))
#        return policy_arrangement
#
#    def get_all_policy_arrangements(self, session=None) -> List[PolicyArrangement]:
#        """
#        Returns all the PolicyArrangements
#
#        :return: The list of PolicyArrangement objects
#        """
#        session = session or self._session_on_init_thread
#        arrangements = session.query(PolicyArrangement).all()
#        return arrangements
#
#    def attach_kfrag_to_saved_arrangement(self, alice, id_as_hex, kfrag, session=None):
#        session = session or self._session_on_init_thread
#        policy_arrangement = session.query(PolicyArrangement).filter_by(id=id_as_hex.encode()).first()
#
#        if policy_arrangement is None:
#            raise NotFound("Can't attach a kfrag to non-existent Arrangement {}".format(id_as_hex))
#
#        if policy_arrangement.alice_verifying_key != alice.stamp:
#            raise alice.SuspiciousActivity
#
#        policy_arrangement.kfrag = bytes(kfrag)
#        self.__commit(session=session)
#
#    def del_policy_arrangement(self, arrangement_id: bytes, session=None) -> int:
#        """
#        Deletes a PolicyArrangement from the Keystore.
#        """
#        session = session or self._session_on_init_thread
#        deleted_records = session.query(PolicyArrangement).filter_by(id=arrangement_id).delete()
#
#        self.__commit(session=session)
#        return deleted_records
#
#    def del_expired_policy_arrangements(self, session=None, now=None) -> int:
#        """
#        Deletes all expired PolicyArrangements from the Keystore.
#        """
#        session = session or self._session_on_init_thread
#        now = now or datetime.now()
#        result = session.query(PolicyArrangement).filter(PolicyArrangement.expiration <= now)
#
#        deleted_records = 0
#        if result.count() > 0:
#            deleted_records = result.delete()
#        self.__commit(session=session)
#        return deleted_records
#
#    #
#    # Work Orders
#    #
#
#    def save_workorder(self,
#                       bob_verifying_key: UmbralPublicKey,
#                       bob_signature: Signature,
#                       arrangement_id: bytes,
#                       session=None
#                       ) -> Workorder:
#        """
#        Adds a Workorder to the keystore.
#        """
#        session = session or self._session_on_init_thread
#
#        new_workorder = Workorder(bob_verifying_key=bytes(bob_verifying_key),
#                                  bob_signature=bob_signature,
#                                  arrangement_id=arrangement_id)
#
#        session.add(new_workorder)
#        self.__commit(session=session)
#        return new_workorder
#
#    def get_workorders(self,
#                       arrangement_id: bytes = None,
#                       bob_verifying_key: bytes = None,
#                       session=None
#                       ) -> List[Workorder]:
#        """
#        Returns a list of Workorders by HRAC.
#        """
#        session = session or self._session_on_init_thread
#        query = session.query(Workorder)
#
#        if not arrangement_id and not bob_verifying_key:
#            workorders = query.all()  # Return all records
#
#        else:
#            # Return arrangement records
#            if arrangement_id:
#                workorders = query.filter_by(arrangement_id=arrangement_id)
#
#            # Return records for Bob
#            else:
#                workorders = query.filter_by(bob_verifying_key=bob_verifying_key)
#
#            if not workorders:
#                raise NotFound
#
#        return list(workorders)
#
#    def del_workorders(self, arrangement_id: bytes, session=None) -> int:
#        """
#        Deletes a Workorder from the Keystore.
#        """
#        session = session or self._session_on_init_thread
#
#        workorders = session.query(Workorder).filter_by(arrangement_id=arrangement_id)
#        deleted = workorders.delete()
#        self.__commit(session=session)
#        return deleted
