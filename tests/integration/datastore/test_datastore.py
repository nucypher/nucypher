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
        # TODO: Mock a `DBWriteError`


# def test_datastore_policy_arrangement_model():
#     arrangement_id = b'test'
#     expiration = maya.now()
#     alice_verifying_key = keypairs.SigningKeypair(generate_keys_if_needed=True).pubkey
# 
#     # TODO: Leaving out KFrag for now since I don't have an easy way to grab one.
#     test_record = PolicyArrangement(arrangement_id=arrangement_id,
#                                     expiration=expiration,
#                                     alice_verifying_key=alice_verifying_key)
# 
#     assert test_record.arrangement_id == arrangement_id
#     assert test_record.expiration == expiration
#     assert alice_verifying_key == alice_verifying_key
#     assert test_record == PolicyArrangement.from_bytes(test_record.to_bytes())
# 
# 
# def test_datastore_workorder_model():
#     bob_keypair = keypairs.SigningKeypair(generate_keys_if_needed=True)
# 
#     arrangement_id = b'test'
#     bob_verifying_key = bob_keypair.pubkey
#     bob_signature = bob_keypair.sign(b'test')
# 
#     test_record = Workorder(arrangement_id=arrangement_id,
#                             bob_verifying_key=bob_verifying_key,
#                             bob_signature=bob_signature)
# 
#     assert test_record.arrangement_id == arrangement_id
#     assert test_record.bob_verifying_key == bob_verifying_key
#     assert test_record.bob_signature == bob_signature
#     assert test_record == Workorder.from_bytes(test_record.to_bytes())
