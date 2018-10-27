import boto3
import pytest
import requests
from moto import mock_s3

from nucypher.characters.lawful import Ursula
from nucypher.config.storages import S3NodeStorage, InMemoryNodeStorage, TemporaryFileBasedNodeStorage, NodeStorage

MOCK_S3_BUCKET_NAME = 'mock-seednodes'
S3_DOMAIN_NAME = 's3.amazonaws.com'


@pytest.fixture(scope='function')
def light_ursula(temp_dir_path):
    node = Ursula(rest_host='127.0.0.1',
                  rest_port=10151,
                  federated_only=True)
    return node


@pytest.fixture(scope='function')
def memory_node_storage():
    _node_storage = InMemoryNodeStorage(character_class=Ursula, federated_only=True)
    _node_storage.initialize()
    return _node_storage


@pytest.fixture(scope='function')
def local_node_storage():
    _node_storage = TemporaryFileBasedNodeStorage(character_class=Ursula, federated_only=True)
    _node_storage.initialize()
    return _node_storage


@mock_s3
def s3_node_storage_factory():
    conn = boto3.resource('s3')
    # We need to create the __bucket since this is all in Moto's 'virtual' AWS account
    conn.create_bucket(Bucket=MOCK_S3_BUCKET_NAME, ACL=S3NodeStorage.S3_ACL)
    _mock_storage = S3NodeStorage(bucket_name=MOCK_S3_BUCKET_NAME,
                                  s3_resource=conn,
                                  character_class=Ursula,
                                  federated_only=True)
    _mock_storage.initialize()
    return _mock_storage


class TestNodeStorageBackends:

    def _read_and_write_to_storage(self, ursula, node_storage):
        # Write Node
        node_storage.save(node=ursula)

        # Read Node
        node_from_storage = node_storage.get(checksum_address=ursula.checksum_public_address,
                                             federated_only=True)
        assert ursula == node_from_storage, "Node storage {} failed".format(node_storage)

        # Save more nodes
        all_known_nodes = set()
        for port in range(10152, 10251):
            node = Ursula(rest_host='127.0.0.1', rest_port=port, federated_only=True)
            node_storage.save(node=node)
            all_known_nodes.add(node)

        # Read all nodes from storage
        all_stored_nodes = node_storage.all(federated_only=True)
        all_known_nodes.add(ursula)
        assert len(all_known_nodes) == len(all_stored_nodes)
        assert all_stored_nodes == all_known_nodes

        # Read random nodes
        for i in range(3):
            random_node = all_known_nodes.pop()
            random_node_from_storage = node_storage.get(checksum_address=random_node.checksum_public_address,
                                                        federated_only=True)
            assert random_node.checksum_public_address == random_node_from_storage.checksum_public_address

        return True

    def _write_and_delete_nodes_in_storage(self, ursula, node_storage):
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
        s3_node_storage_factory
    ])
    @mock_s3
    def test_delete_node_in_storage(self, light_ursula, storage_factory):
        assert self._write_and_delete_nodes_in_storage(ursula=light_ursula, node_storage=storage_factory())

    @pytest.mark.parametrize("storage_factory", [
        memory_node_storage,
        local_node_storage,
        s3_node_storage_factory
    ])
    @mock_s3
    def test_read_and_write_to_storage(self, light_ursula, storage_factory):
        assert self._read_and_write_to_storage(ursula=light_ursula, node_storage=storage_factory())


class TestS3NodeStorageDirect:

    @mock_s3
    def test_generate_presigned_url(self, light_ursula):
        s3_node_storage = s3_node_storage_factory()
        s3_node_storage.save(node=light_ursula)
        presigned_url = s3_node_storage.generate_presigned_url(checksum_address=light_ursula.checksum_public_address)

        assert S3_DOMAIN_NAME in presigned_url
        assert MOCK_S3_BUCKET_NAME in presigned_url
        assert light_ursula.checksum_public_address in presigned_url

        moto_response = requests.get(presigned_url)
        assert moto_response.status_code == 200
