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
import pytest
from datetime import datetime

from nucypher.datastore import datastore, keypairs


@pytest.mark.usefixtures('testerchain')
def test_key_sqlite_datastore(test_datastore, federated_bob):

    # Test add pubkey
    test_datastore.add_key(federated_bob.stamp, is_signing=True)

    # Test get pubkey
    query_key = test_datastore.get_key(federated_bob.stamp.fingerprint())
    assert bytes(federated_bob.stamp) == bytes(query_key)

    # Test del pubkey
    test_datastore.del_key(federated_bob.stamp.fingerprint())
    with pytest.raises(datastore.NotFound):
        del_key = test_datastore.get_key(federated_bob.stamp.fingerprint())


def test_policy_arrangement_sqlite_datastore(test_datastore):
    alice_keypair_sig = keypairs.SigningKeypair(generate_keys_if_needed=True)

    arrangement_id = b'test'

    # Test add PolicyArrangement
    new_arrangement = test_datastore.add_policy_arrangement(
            datetime.utcnow(), b'test', arrangement_id, alice_verifying_key=alice_keypair_sig.pubkey,
            alice_signature=b'test'
    )

    # Test get PolicyArrangement
    query_arrangement = test_datastore.get_policy_arrangement(arrangement_id)
    assert new_arrangement == query_arrangement

    # Test del PolicyArrangement
    test_datastore.del_policy_arrangement(arrangement_id)
    with pytest.raises(datastore.NotFound):
        del_key = test_datastore.get_policy_arrangement(arrangement_id)


def test_workorder_sqlite_datastore(test_datastore):
    bob_keypair_sig1 = keypairs.SigningKeypair(generate_keys_if_needed=True)
    bob_keypair_sig2 = keypairs.SigningKeypair(generate_keys_if_needed=True)

    arrangement_id = b'test'

    # Test add workorder
    new_workorder1 = test_datastore.save_workorder(bob_keypair_sig1.pubkey, b'test0', arrangement_id)
    new_workorder2 = test_datastore.save_workorder(bob_keypair_sig2.pubkey, b'test1', arrangement_id)

    # Test get workorder
    query_workorders = test_datastore.get_workorders(arrangement_id)
    assert {new_workorder1, new_workorder2}.issubset(query_workorders)

    # Test del workorder
    deleted = test_datastore.del_workorders(arrangement_id)
    assert deleted > 0
    assert len(test_datastore.get_workorders(arrangement_id)) == 0
