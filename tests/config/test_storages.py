import boto3
import pytest
from moto import mock_s3

from nucypher.characters.lawful import Ursula
from nucypher.config.storages import S3NodeStorage, InMemoryNodeStorage, LocalFileBasedNodeStorage, NODE_STORAGES, \
    TemporaryFileBasedNodeStorage, NodeStorage

MOCK_S3_BUCKET_NAME = 'mock-bootnodes'


@pytest.fixture(scope='module')
def light_ursula(temp_dir_path):
    node = Ursula(rest_host='127.0.0.1',
                  rest_port=10151,
                  federated_only=True)
    return node


#
# Factories
#

def memory_node_storage():
    _node_storage = InMemoryNodeStorage(character_class=Ursula, federated_only=True)
    _node_storage.initialize()
    return _node_storage


def local_node_storage():
    _node_storage = TemporaryFileBasedNodeStorage(character_class=Ursula, federated_only=True)
    _node_storage.initialize()
    return _node_storage


def s3_node_storage():
    @mock_s3
    def __mock_s3():
        conn = boto3.resource('s3')
        # We need to create the bucket since this is all in Moto's 'virtual' AWS account
        conn.create_bucket(Bucket=MOCK_S3_BUCKET_NAME)
        _mock_storage = S3NodeStorage(bucket_name=MOCK_S3_BUCKET_NAME,
                                      s3_resource=conn,
                                      character_class=Ursula,
                                      federated_only=True)
        return _mock_storage
    _node_storage = __mock_s3()
    _node_storage.initialize()
    return _node_storage


#
# Test Helpers
#

def _read_and_write_to_storage(ursula, node_storage):
    # Write Node
    node_storage.save(node=ursula)

    # Read Node
    node_from_storage = node_storage.get(checksum_address=ursula.checksum_public_address,
                                         federated_only=True)
    assert ursula == node_from_storage, "Node storage {} failed".format(node_storage)

    # Save more nodes
    all_known_nodes = set()
    for port in range(10152, 10155):
        node = Ursula(rest_host='127.0.0.1', rest_port=port, federated_only=True)
        node_storage.save(node=node)
        all_known_nodes.add(node)

    # Read all nodes from storage
    all_stored_nodes = node_storage.all(federated_only=True)
    all_known_nodes.add(ursula)

    assert all_stored_nodes == all_known_nodes
    return True


def _write_and_delete_nodes_in_storage(ursula, node_storage):
    # Write Node
    node_storage.save(node=ursula)

    # Delete Node
    node_storage.remove(checksum_address=ursula.checksum_public_address)

    # Read Node
    with pytest.raises(NodeStorage.UnknownNode):
        _node_from_storage = node_storage.get(checksum_address=ursula.checksum_public_address,
                                              federated_only=True)

    # Read all nodes from storage
    all_stored_nodes = node_storage.all(federated_only=True)
    assert all_stored_nodes == set()
    return True


#
# Storage Backed Tests
#

@pytest.mark.parametrize("storage_factory", [
    memory_node_storage,
    local_node_storage,
    s3_node_storage
])
@mock_s3
def test_delete_node_in_storage(light_ursula, storage_factory):
    assert _write_and_delete_nodes_in_storage(ursula=light_ursula, node_storage=storage_factory())


@pytest.mark.parametrize("storage_factory", [
    memory_node_storage,
    local_node_storage,
    s3_node_storage
])
@mock_s3
def test_read_and_write_to_storage(light_ursula, storage_factory):
    assert _read_and_write_to_storage(ursula=light_ursula, node_storage=storage_factory())
