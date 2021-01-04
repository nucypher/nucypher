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
import msgpack
import pytest
import tempfile
from datetime import datetime
from nucypher.datastore import datastore
from nucypher.datastore.base import DatastoreRecord, RecordField


class TestRecord(DatastoreRecord):
    __test__ = False    # For pytest

    _test = RecordField(bytes)
    _test_date = RecordField(datetime,
            encode=lambda val: datetime.isoformat(val).encode(),
            decode=lambda val: datetime.fromisoformat(val.decode()))


def test_datastore_create():
    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)
    assert storage.LMDB_MAP_SIZE == 1_000_000_000_000
    assert storage.db_path == temp_path
    assert storage._Datastore__db_env.path() == temp_path


def test_datastore_describe(mock_or_real_datastore):

    storage = mock_or_real_datastore

    #
    # Tests for `Datastore.describe`
    #

    # Getting writeable access to a record can be done by setting `writeable` to `True`.
    # `writeable` is, by default, `False`.
    # In the event a record doesn't exist, this will raise a `RecordNotFound` error iff `writeable=False`.
    with pytest.raises(datastore.RecordNotFound):
        with storage.describe(TestRecord, 'test_id') as test_record:
            should_error = test_record.test

    # Reading a non-existent field from a writeable record is an error
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            what_is_this = test_record.test

    # Writing to a, previously nonexistent record, with a valid field works!
    with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
        test_record.test = b'test data'
        assert test_record.test == b'test data'

    # Check that you can't reuse the record instance to write outside the context manager
    with pytest.raises(TypeError):
        test_record.test = b'should not write'

    # Nor can you read outside the context manager
    with pytest.raises(lmdb.Error):
        should_error = test_record.test

    # Records can also have ints as IDs
    with storage.describe(TestRecord, 1337, writeable=True) as test_record:
        test_record.test = b'test int ID'
        assert test_record.test == b'test int ID'

    # Writing to a non-existent field errors
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            test_record.nonexistent_field = b'this will error'

    # Writing the wrong type to a field errors
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            test_record.test = 1234

    # Check that nothing was written
    with storage.describe(TestRecord, 'test_id') as test_record:
        assert test_record.test != 1234

    # Any unhandled errors in the context manager results in a transaction abort
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            # Valid write
            test_record.test = b'this will not persist'
            # Erroneous write causing an abort
            test_record.nonexistent = b'causes an error and aborts the write'

    # Check that nothing was written from the aborted transaction above.
    with storage.describe(TestRecord, 'test_id') as test_record:
        assert test_record.test == b'test data'

    # However, a handled error will not cause an abort.
    with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
        # Valid operation
        test_record.test = b'this will persist'
        try:
            # Maybe we don't know that this field exists or not?
            # Erroneous, but handled, operation -- doesn't cause an abort
            should_error = test_record.bad_read
        except TypeError:
            pass

    # Because we handled the `TypeError`, the write persists.
    with storage.describe(TestRecord, 'test_id') as test_record:
        assert test_record.test == b'this will persist'

    # Be aware: if you don't handle _all the errors_, then the transaction will abort:
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            # Valid operation
            test_record.test = b'this will not persist'
            try:
                # We handle this one correctly
                # Erroneous, but handled, operation -- doesn't cause an abort
                this_will_not_abort = test_record.bad_read
            except TypeError:
                pass

            # However, we don't handle this one correctly
            # Erroneous UNHANDLED operation -- causes an abort
            this_WILL_abort = test_record.bad_read

    # The valid operation did not persist due to the unhandled error, despite
    # the other one being handled.
    with storage.describe(TestRecord, 'test_id') as test_record:
        assert test_record.test != b'this will not persist'

    # An applicable demonstration:
    # Let's imagine we don't know if a `TestRecord` identified by `new_id` exists.
    # If we want to conditionally modify it, we can do as follows:
    with storage.describe(TestRecord, 'new_id', writeable=True) as new_test_record:
        try:
            # Assume the record exists
            my_test_data = new_test_record.test
            # Do something with my_test_data
        except AttributeError:
            # We handle the case that there's no record for `new_test_record.test`
            # and write to it.
            new_test_record.test = b'now it exists :)'

    # And proof that it worked:
    with storage.describe(TestRecord, 'new_id') as new_test_record:
        assert new_test_record.test == b'now it exists :)'


def test_datastore_query_by(mock_or_real_datastore):

    storage = mock_or_real_datastore

    # Make two test record classes
    class FooRecord(DatastoreRecord):
        _foo = RecordField(bytes)

    class BarRecord(DatastoreRecord):
        _foo = RecordField(bytes)
        _bar = RecordField(bytes)

    # We won't add this one
    class NoRecord(DatastoreRecord):
        _nothing = RecordField(bytes)

    # Create them
    with storage.describe(FooRecord, 1, writeable=True) as rec:
        rec.foo = b'one record'
    with storage.describe(FooRecord, 'two', writeable=True) as rec:
        rec.foo = b'another record'
    with storage.describe(FooRecord, 'three', writeable=True) as rec:
        rec.foo = b'another record'

    with storage.describe(BarRecord, 1, writeable=True) as rec:
        rec.bar = b'one record'
    with storage.describe(BarRecord, 'two', writeable=True) as rec:
        rec.foo = b'foo two record'
        rec.bar = b'two record'

    # Let's query!
    with storage.query_by(FooRecord) as records:
        assert len(records) == 3
        assert type(records) == list
        assert records[0]._DatastoreRecord__writeable is False
        assert records[1]._DatastoreRecord__writeable is False
        assert records[2]._DatastoreRecord__writeable is False

    # Try with BarRecord
    with storage.query_by(BarRecord) as records:
        assert len(records) == 2

    # Try to query for non-existent records
    with pytest.raises(datastore.RecordNotFound):
        with storage.query_by(NoRecord) as records:
            assert len(records) == 'this never gets executed cause it raises'

    # Queries without writeable are read only
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.query_by(FooRecord) as records:
            records[0].foo = b'this should error'

    # Let's query by specific record and field
    with storage.query_by(BarRecord, filter_field='foo') as records:
        assert len(records) == 1

    # Query for a non-existent field in an existing record
    with pytest.raises(datastore.RecordNotFound):
        with storage.query_by(FooRecord, filter_field='bar') as records:
            assert len(records) == 'this never gets executed cause it raises'

    # Query for a non-existent field that is _similar to an existing field_
    with pytest.raises(datastore.RecordNotFound):
        with storage.query_by(FooRecord, filter_field='fo') as records:
            assert len(records) == 'this never gets executed cause it raises'

    # Query for a field with a filtering function
    # When querying with a field _and_ a filtering function, the `filter_func`
    # callable is given the field value you specified.
    # We throw a `isinstance` in there to ensure that the type given is a field value and not a record
    filter_func = lambda field_val: not isinstance(field_val, DatastoreRecord) and field_val == b'another record'
    with storage.query_by(FooRecord, filter_field='foo', filter_func=filter_func) as records:
        assert len(records) == 2
        assert records[0].foo == b'another record'
        assert records[1].foo == b'another record'

    # Query with _only_ a filter func.
    # This filter_func will receive a `DatastoreRecord` instance that is readonly
    filter_func = lambda field_rec: isinstance(field_rec, DatastoreRecord) and field_rec.foo == b'one record'
    with storage.query_by(FooRecord, filter_func=filter_func) as records:
        assert len(records) == 1
        assert records[0].foo == b'one record'

        # This record isn't writeable
        with pytest.raises(TypeError):
            records[0].foo = b'this will error'

    # Make a writeable query on BarRecord
    with storage.query_by(BarRecord, writeable=True) as records:
        records[0].bar = b'this writes'
        records[1].bar = b'this writes'
        assert records[0].bar == b'this writes'
        assert records[1].bar == b'this writes'

    # Writeable queries on non-existant records error
    with pytest.raises(datastore.RecordNotFound):
        with storage.query_by(NoRecord, writeable=True) as records:
            assert len(records) == 'this never gets executed'


def test_datastore_record_read(mock_or_real_lmdb_env):
    db_env = mock_or_real_lmdb_env
    with db_env.begin() as db_tx:
        # Check the default attrs.
        test_rec = TestRecord(db_tx, 'testing', writeable=False)
        assert test_rec._record_id == 'testing'
        assert test_rec._DatastoreRecord__db_transaction == db_tx
        assert test_rec._DatastoreRecord__writeable == False
        assert test_rec._DatastoreRecord__storagekey == 'TestRecord:{record_field}:{record_id}'

        # Reading an attr with no RecordField should error
        with pytest.raises(TypeError):
            should_error = test_rec.nonexistant_field

        # Reading when no records exist errors
        with pytest.raises(AttributeError):
            should_error = test_rec.test

        # The record is not writeable
        with pytest.raises(TypeError):
            test_rec.test = b'should error'


def test_datastore_record_write(mock_or_real_lmdb_env):
    # Test writing
    db_env = mock_or_real_lmdb_env
    with db_env.begin(write=True) as db_tx:
        test_rec = TestRecord(db_tx, 'testing', writeable=True)
        assert test_rec._DatastoreRecord__writeable == True

        # Write an invalid serialization of `test` and test retrieving it is
        # a TypeError
        db_tx.put(b'TestRecord:test:testing', msgpack.packb(1234))
        with pytest.raises(TypeError):
            should_error = test_rec.test

        # Writing an invalid serialization of a field is a `TypeError`
        with pytest.raises(TypeError):
            test_rec.test = 1234

        # Test deleting a field
        test_rec.test = None
        with pytest.raises(AttributeError):
            should_error = test_rec.test

        # Test writing a valid field and getting it.
        test_rec.test = b'good write'
        assert test_rec.test == b'good write'
        assert msgpack.unpackb(db_tx.get(b'TestRecord:test:testing')) == b'good write'
        # TODO: Mock a `DBWriteError`

    # Test abort
    # Transaction context manager attempts to commit the transaction at `__exit__()`,
    # since there were no errors caught, but it's already been aborted,
    # so `lmdb.Error` is raised.
    with pytest.raises(lmdb.Error):
        with db_env.begin(write=True) as db_tx:
            test_rec = TestRecord(db_tx, 'testing', writeable=True)
            test_rec.test = b'should not be set'
            db_tx.abort()

    # After abort, the value should still be the one before the previous `put`
    with db_env.begin() as db_tx:
        test_rec = TestRecord(db_tx, 'testing', writeable=False)
        assert test_rec.test == b'good write'


def test_key_tuple():
    partial_key = datastore.DatastoreKey.from_bytestring(b'TestRecord:test_field')
    assert partial_key.record_type == 'TestRecord'
    assert partial_key.record_field == 'test_field'
    assert partial_key.record_id is None

    full_key = datastore.DatastoreKey.from_bytestring(b'TestRecord:test_field:test_id')
    assert full_key.record_type == 'TestRecord'
    assert full_key.record_field == 'test_field'
    assert full_key.record_id == 'test_id'

    # Full keys can match partial key strings and other full key strings
    assert full_key.compare_key(b'TestRecord:test_field:test_id') is True
    assert full_key.compare_key(b'TestRecord:test_field') is True
    assert full_key.compare_key(b'TestRecord:') is True
    assert full_key.compare_key(b'BadRecord:') is False
    assert full_key.compare_key(b'BadRecord:bad_field') is False
    assert full_key.compare_key(b'BadRecord:bad_field:bad_id') is False

    # Partial keys can't match key strings that are more complete than themselves
    assert partial_key.compare_key(b'TestRecord:test_field:test_id') is False
    assert partial_key.compare_key(b'TestRecord:test_field') is True
    assert partial_key.compare_key(b'TestRecord') is True
    assert partial_key.compare_key(b'BadRecord') is False
    assert partial_key.compare_key(b'BadRecord:bad_field') is False
    assert partial_key.compare_key(b'BadRecord:bad_field:bad_id') is False

    # IDs as ints
    int_id_key = datastore.DatastoreKey.from_bytestring(b'TestRecord:test_field:1')
    assert int_id_key.record_id == 1
    assert type(int_id_key.record_id) == int
