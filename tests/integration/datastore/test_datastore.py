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
import msgpack
import pytest
import tempfile
from datetime import datetime

from nucypher.datastore import datastore, keypairs
from nucypher.datastore.base import DatastoreRecord, RecordField
from nucypher.datastore.models import PolicyArrangement, Workorder


def test_datastore():
    class TestRecord(DatastoreRecord):
        _test = RecordField(bytes)
        _test_date = RecordField(datetime,
                encode=lambda val: datetime.isoformat(val).encode(),
                decode=lambda val: datetime.fromisoformat(val.decode()))

    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)
    assert storage.LMDB_MAP_SIZE == 1_000_000_000_000
    assert storage.db_path == temp_path
    assert storage._Datastore__db_env.path() == temp_path

    # Test writing
    # Writing to a valid field works!
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

    # An error in the context manager results in a transaction abort
    with pytest.raises(datastore.DatastoreTransactionError):
        with storage.describe(TestRecord, 'test_id', writeable=True) as test_record:
            # Valid write
            test_record.test = b'this will not persist'
            # Erroneous write causing an abort
            test_record.nonexistent = b'causes an error and aborts the write'

    # Test reading
    # Getting read-only access to a record can be done by not setting `writeable` to `True`.
    # `writeable` is, by default, `False`.
    # Check that nothing was written from the aborted transaction above.
    with storage.describe(TestRecord, 'test_id') as test_record:
        assert test_record.test == b'test data'

    # In the event a record doesn't exist, this will raise a `RecordNotFound` error iff `writeable=False`.
    with pytest.raises(datastore.RecordNotFound):
        with storage.describe(TestRecord, 'nonexistent') as test_record:
            should_error = test_record.test


def test_datastore_record_read():
    class TestRecord(DatastoreRecord):
        _test = RecordField(bytes)
        _test_date = RecordField(datetime,
                encode=lambda val: datetime.isoformat(val).encode(),
                decode=lambda val: datetime.fromisoformat(val.decode()))

    db_env = lmdb.open(tempfile.mkdtemp())
    with db_env.begin() as db_tx:
        # Check the default attrs.
        test_rec = TestRecord(db_tx, 'testing', writeable=False)
        assert test_rec._record_id == 'testing'
        assert test_rec._fields == ['test', 'test_date']
        assert test_rec._DatastoreRecord__db_tx == db_tx
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


def test_datastore_record_write():
    class TestRecord(DatastoreRecord):
        _test = RecordField(bytes)
        _test_date = RecordField(datetime,
                encode=lambda val: datetime.isoformat(val).encode(),
                decode=lambda val: datetime.fromisoformat(val.decode()))

    # Test writing
    db_env = lmdb.open(tempfile.mkdtemp())
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

        # Test writing a valid field and getting it.
        test_rec.test = b'good write'
        assert test_rec.test == b'good write'
        assert msgpack.unpackb(db_tx.get(b'TestRecord:test:testing')) == b'good write'
        # TODO: Mock a `DBWriteError`

    # Test abort
    with pytest.raises(lmdb.Error):
        with db_env.begin(write=True) as db_tx:
            test_rec = TestRecord(db_tx, 'testing', writeable=True)
            test_rec.test = b'should not be set'
            db_tx.abort()

    # After abort, the value should still be the one before the previous `put`
    with db_env.begin() as db_tx:
        test_rec = TestRecord(db_tx, 'testing', writeable=False)
        assert test_rec.test == b'good write'


def test_datastore_policy_arrangement_model():
    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)

    arrangement_id_hex = 'beef'
    expiration = maya.now()
    alice_verifying_key = keypairs.SigningKeypair(generate_keys_if_needed=True).pubkey
 
    # TODO: Leaving out KFrag for now since I don't have an easy way to grab one.
    with storage.describe(PolicyArrangement, arrangement_id_hex, writeable=True) as policy_arrangement:
        policy_arrangement.arrangement_id = bytes.fromhex(arrangement_id_hex)
        policy_arrangement.expiration = expiration
        policy_arrangement.alice_verifying_key = alice_verifying_key

    with storage.describe(PolicyArrangement, arrangement_id_hex) as policy_arrangement:
        assert policy_arrangement.arrangement_id == bytes.fromhex(arrangement_id_hex)
        assert policy_arrangement.expiration == expiration
        assert policy_arrangement.alice_verifying_key == alice_verifying_key
 
 
def test_datastore_workorder_model():
    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)
    bob_keypair = keypairs.SigningKeypair(generate_keys_if_needed=True)
 
    arrangement_id_hex = 'beef'
    bob_verifying_key = bob_keypair.pubkey
    bob_signature = bob_keypair.sign(b'test')
 
    with storage.describe(Workorder, arrangement_id_hex, writeable=True) as work_order:
        work_order.arrangement_id = bytes.fromhex(arrangement_id_hex)
        work_order.bob_verifying_key = bob_verifying_key
        work_order.bob_signature = bob_signature
 
    with storage.describe(Workorder, arrangement_id_hex) as work_order:
        assert work_order.arrangement_id == bytes.fromhex(arrangement_id_hex)
        assert work_order.bob_verifying_key == bob_verifying_key
        assert work_order.bob_signature == bob_signature
