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
from contextlib import contextmanager, suppress
from functools import partial
from typing import Any, Callable, Generator, List, NamedTuple, Optional, Type, Union

from nucypher.datastore.base import DatastoreRecord, DBWriteError

DatastoreQueryResult = Generator[List[Type['DatastoreRecord']], None, None]

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


class DatastoreKey(NamedTuple):
    """
    Used for managing keys when querying the datastore.
    """
    record_type: Optional[str] = None
    record_field: Optional[str] = None
    record_id: Optional[Union[bytes, int]] = None

    @classmethod
    def from_bytestring(cls, key_bytestring: bytes) -> 'DatastoreKey':
        key_parts = key_bytestring.decode().split(':')
        with suppress(ValueError):
            # If the ID can be an int, we convert it
            key_parts[-1] = int(key_parts[-1])
        return cls(*key_parts)

    def compare_key(self, key_bytestring: bytes) -> bool:
        """
        This method compares a key to another key given a key's bytestring.
        Usually, the `key_bytestring` will be a query key, and the `self`
        key will be a key in the `Datastore`.

        The logic below offers precedence when performing matches on a query.
        We _prefer_ the `other_key` over `self`.
        As such, if `other_key` doesn't specify a key attr (it will be None),
        we will take the key attr conferred by `self`.

        Specifically, this allows us to match partial keys to specific keys,
        where the `Datastore` will _always_ return specific keys, but queries
        will almost always be partial keys.
        """
        other_key = DatastoreKey.from_bytestring(key_bytestring)
        return self.record_type == (other_key.record_type or self.record_type) and \
               self.record_field == (other_key.record_field or self.record_field) and \
               self.record_id == (other_key.record_id or self.record_id)


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
    def describe(self,
                 record_type: Type['DatastoreRecord'],
                 record_id: Union[int, str],
                 writeable: bool = False) -> Type['DatastoreRecord']:
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
        with suppress(ValueError):
            # If the ID can be converted to an int, we do it.
            record_id = int(record_id)

        with self.__db_env.begin(write=writeable) as datastore_tx:
            record = record_type(datastore_tx, record_id, writeable=writeable)
            try:
                yield record
            except (AttributeError, TypeError, DBWriteError) as tx_err:
                # Handle `RecordNotFound` cases when `writeable` is `False`.
                if not writeable and isinstance(tx_err, AttributeError):
                    raise RecordNotFound(tx_err)
                raise DatastoreTransactionError(f'An error was encountered during the transaction (no data was written): {tx_err}')
            finally:
                # Now we ensure that the record is not writeable
                record.__dict__['_DatastoreRecord__writeable'] = False

    @contextmanager
    def query_by(self,
              record_type: Type['DatastoreRecord'],
              filter_func: Optional[Callable[[Union[Any, Type['DatastoreRecord']]], bool]] = None,
              filter_field: str = "",
              writeable: bool = False,
              ) -> DatastoreQueryResult:
        """
        Performs a query on the datastore for the record by `record_type`.

        An optional `filter_func` callable will take the decoded field
        specified by the optional arg `filter_field` (see below) for the given
        `record_type` iff the `filter_field` has been provided.
        If no `filter_field` has been provided, then the `filter_func` will
        receive a _readonly_ `DatastoreRecord`.

        An optional `filter_field` can be provided as a `str` to perform a
        query on a specific field for a `record_type`. This will cause the
        `filter_func` to receive the decoded `filter_field` per the `record_type`.
        Additionally, providing a `filter_field` will limit the query to
        iterating over only the subset of records specific to that field.

        If records can't be found, this method will raise `RecordNotFound`.
        """
        valid_records = set()
        with self.__db_env.begin(write=writeable) as datastore_tx:
            db_cursor = datastore_tx.cursor()

            # Set the cursor to the closest key (if it exists) by the query params.
            #
            # By providing a `filter_field`, the query will immediately be
            # limited to the subset of keys for the `filter_field`.
            query_key = f'{record_type.__name__}:{filter_field}'.encode()
            if not db_cursor.set_range(query_key):
                # The cursor couldn't identify any records by the key
                raise RecordNotFound(f"No records exist for the key from the specified query parameters: '{query_key}'")

            # Check if the record at the cursor is valid for the query
            curr_key = DatastoreKey.from_bytestring(db_cursor.key())
            if not curr_key.compare_key(query_key):
                raise RecordNotFound(f"No records exist for the key from the specified query parameters: '{query_key}'")

            # Everything checks out, let's begin iterating!
            # We begin by comparing the current key to the query key.
            # If the key doesn't match the query key, we know that there are
            # no records for the query because lmdb orders the keys lexicographically.
            # Ergo, if the current key doesn't match the query key, we know
            # we have gone beyond the relevant keys and can `break` the loop.
            # Additionally, if the record is already in the `valid_records`
            # set (identified by the `record_id`, we call `continue`.
            for db_key in db_cursor.iternext(keys=True, values=False):
                curr_key = DatastoreKey.from_bytestring(db_key)
                if not curr_key.compare_key(query_key):
                    break
                elif curr_key.record_id in valid_records:
                    continue

                record = partial(record_type, datastore_tx, curr_key.record_id)

                # We pass the field to the filter_func if `filter_field` and
                # `filter_func` are both provided. In the event that the
                # given `filter_field` doesn't exist for the record or the
                # `filter_func` returns `False`, we call `continue`.
                if filter_field and filter_func:
                    try:
                        field = getattr(record(writeable=False), filter_field)
                    except (TypeError, AttributeError):
                        continue
                    else:
                        if not filter_func(field):
                            continue

                # If only a filter_func is given, we pass a readonly record to it.
                # Likewise to the above, if `filter_func` returns `False`, we
                # call `continue`.
                elif filter_func:
                    if not filter_func(record(writeable=False)):
                        continue

                # Finally, having a record that satisfies the above conditional
                # constraints, we can add the record to the set
                valid_records.add(record(writeable=writeable))

            # If after the iteration we have no records, we raise `RecordNotFound`
            if len(valid_records) == 0:
                raise RecordNotFound(f"No records exist for the key from the specified query parameters: '{query_key}'")
            # We begin the context manager try/finally block
            try:
                # At last, we yield the queried records
                yield list(valid_records)
            except (AttributeError, TypeError, DBWriteError) as tx_err:
                # Handle `RecordNotFound` cases when `writeable` is `False`.
                if not writeable and isinstance(tx_err, AttributeError):
                    raise RecordNotFound(tx_err)
                raise DatastoreTransactionError(f'An error was encountered during the transaction (no data was written): {tx_err}')
            finally:
                for record in valid_records:
                    record.__dict__['_DatastoreRecord__writeable'] = False
