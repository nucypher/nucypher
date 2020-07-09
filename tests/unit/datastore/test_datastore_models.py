import maya
import pytest
import tempfile

from nucypher.datastore import datastore, keypairs
from nucypher.datastore.models import PolicyArrangement, TreasureMap, Workorder


def test_policy_arrangement_model():
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

    # Now let's `delete` it
    with storage.describe(PolicyArrangement, arrangement_id_hex, writeable=True) as policy_arrangement:
        policy_arrangement.delete()

        # Should be deleted now.
        with pytest.raises(AttributeError):
            should_error = policy_arrangement.arrangement_id
 
 
def test_workorder_model():
    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)
    bob_keypair = keypairs.SigningKeypair(generate_keys_if_needed=True)
 
    arrangement_id_hex = 'beef'
    bob_verifying_key = bob_keypair.pubkey
    bob_signature = bob_keypair.sign(b'test')
 
    # Test create
    with storage.describe(Workorder, arrangement_id_hex, writeable=True) as work_order:
        work_order.arrangement_id = bytes.fromhex(arrangement_id_hex)
        work_order.bob_verifying_key = bob_verifying_key
        work_order.bob_signature = bob_signature

    with storage.describe(Workorder, arrangement_id_hex) as work_order:
        assert work_order.arrangement_id == bytes.fromhex(arrangement_id_hex)
        assert work_order.bob_verifying_key == bob_verifying_key
        assert work_order.bob_signature == bob_signature

    # Test delete
    with storage.describe(Workorder, arrangement_id_hex, writeable=True) as work_order:
        work_order.delete()

        # Should be deleted now.
        with pytest.raises(AttributeError):
            should_error = work_order.arrangement_id


def test_treasure_map_model():
    temp_path = tempfile.mkdtemp()
    storage = datastore.Datastore(temp_path)

    treasure_map_id_hex = 'beef'
    fake_treasure_map_data = b'My Little TreasureMap'

    with storage.describe(TreasureMap, treasure_map_id_hex, writeable=True) as treasure_map:
        treasure_map.treasure_map = fake_treasure_map_data

    with storage.describe(TreasureMap, treasure_map_id_hex) as treasure_map:
        assert treasure_map.treasure_map == b'My Little TreasureMap'

    # Test delete
    with storage.describe(TreasureMap, treasure_map_id_hex, writeable=True) as treasure_map:
        treasure_map.delete()

        # Should be deleted now.
        with pytest.raises(AttributeError):
            should_error = treasure_map.treasure_map
