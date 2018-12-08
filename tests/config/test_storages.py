"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import contextlib
import os

import boto3
import pytest
import requests
from moto import mock_s3

from nucypher.characters.lawful import Ursula
from nucypher.config.storages import (
    S3NodeStorage,
    ForgetfulNodeStorage,
    TemporaryFileBasedNodeStorage,
    NodeStorage
)
from nucypher.utilities.sandbox.constants import MOCK_URSULA_DB_FILEPATH

MOCK_S3_BUCKET_NAME = 'mock-seednodes'
S3_DOMAIN_NAME = 's3.amazonaws.com'


class BaseTestNodeStorageBackends:

    @pytest.fixture(scope='class')
    def light_ursula(temp_dir_path):
        db_filepath = 'ursula-{}.db'.format(10151)
        try:
            node = Ursula(rest_host='127.0.0.1',
                          rest_port=10151,
                          db_filepath=MOCK_URSULA_DB_FILEPATH,
                          federated_only=True)

            yield node
        finally:
            with contextlib.suppress(Exception):
                os.remove(db_filepath)

    character_class = Ursula
    federated_only = True
    storage_backend = NotImplemented

    def _read_and_write_metadata(self, ursula, node_storage):
        # Write Node
        node_storage.store_node_metadata(node=ursula)

        # Read Node
        node_from_storage = node_storage.get(checksum_address=ursula.checksum_public_address,
                                             federated_only=True)
        assert ursula == node_from_storage, "Node storage {} failed".format(node_storage)

        # Save more nodes
        all_known_nodes = set()
        for port in range(10152, 10251):
            node = Ursula(rest_host='127.0.0.1', db_filepath=MOCK_URSULA_DB_FILEPATH, rest_port=port, federated_only=True)
            node_storage.store_node_metadata(node=node)
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

    def _write_and_delete_metadata(self, ursula, node_storage):
        # Write Node
        node_storage.store_node_metadata(node=ursula)

        # Delete Node
        node_storage.remove(checksum_address=ursula.checksum_public_address, certificate=False)

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

    def test_delete_node_in_storage(self, light_ursula):
        assert self._write_and_delete_metadata(ursula=light_ursula, node_storage=self.storage_backend)

    def test_read_and_write_to_storage(self, light_ursula):
        assert self._read_and_write_metadata(ursula=light_ursula, node_storage=self.storage_backend)


class TestInMemoryNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = ForgetfulNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                           federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()


class TestTemporaryFileBasedNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = TemporaryFileBasedNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                                    federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()


@pytest.mark.skip("Fails after moto / boto update: Needs investigation")
class TestS3NodeStorageDirect(BaseTestNodeStorageBackends):

    @mock_s3
    def setup_class(self):
        conn = boto3.resource('s3')
        # We need to create the __bucket since this is all in Moto's 'virtual' AWS account
        conn.create_bucket(Bucket=MOCK_S3_BUCKET_NAME, ACL=S3NodeStorage.S3_ACL)

        storage_backend = S3NodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                        federated_only=BaseTestNodeStorageBackends.federated_only,
                                        bucket_name=MOCK_S3_BUCKET_NAME,
                                        s3_resource=conn
                                        )
        storage_backend.initialize()

    @mock_s3
    def test_generate_presigned_url(self, light_ursula):
        s3_node_storage = self.s3_node_storage_factory()
        s3_node_storage.store_node_metadata(node=light_ursula)
        presigned_url = s3_node_storage.generate_presigned_url(checksum_address=light_ursula.checksum_public_address)

        assert S3_DOMAIN_NAME in presigned_url
        assert MOCK_S3_BUCKET_NAME in presigned_url
        assert light_ursula.checksum_public_address in presigned_url

        moto_response = requests.get(presigned_url)
        assert moto_response.status_code == 200

    @mock_s3
    def test_read_and_write_to_storage(self, light_ursula):
        s3_node_storage = self.s3_node_storage_factory()

        # Write Node
        s3_node_storage.store_node_metadata(node=light_ursula)

        # Read Node
        node_from_storage = s3_node_storage.get(checksum_address=light_ursula.checksum_public_address,
                                                federated_only=True)
        assert light_ursula == node_from_storage, "Node storage {} failed".format(s3_node_storage)

        # Save more nodes
        all_known_nodes = set()
        for port in range(10152, 10251):
            node = Ursula(rest_host='127.0.0.1', rest_port=port, federated_only=True)
            s3_node_storage.store_node_metadata(node=node)
            all_known_nodes.add(node)

        # Read all nodes from storage
        all_stored_nodes = s3_node_storage.all(federated_only=True)
        all_known_nodes.add(light_ursula)
        assert len(all_known_nodes) == len(all_stored_nodes)
        assert all_stored_nodes == all_known_nodes

        # Read random nodes
        for i in range(3):
            random_node = all_known_nodes.pop()
            random_node_from_storage = s3_node_storage.get(checksum_address=random_node.checksum_public_address,
                                                           federated_only=True)
            assert random_node.checksum_public_address == random_node_from_storage.checksum_public_address

        return True

    @mock_s3
    def test_write_and_delete_nodes_in_storage(self, light_ursula):
        s3_node_storage = self.s3_node_storage_factory()

        # Write Node
        s3_node_storage.store_node_metadata(node=light_ursula)

        # Delete Node
        s3_node_storage.remove(checksum_address=light_ursula.checksum_public_address)

        # Read Node
        with pytest.raises(NodeStorage.UnknownNode):
            _node_from_storage = s3_node_storage.get(checksum_address=light_ursula.checksum_public_address,
                                                     federated_only=True)

        # Read all nodes from storage
        all_stored_nodes = s3_node_storage.all(federated_only=True)
        assert all_stored_nodes == set()
        return True
