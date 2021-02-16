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

import os
import pytest
import tempfile

from nucypher.characters.lawful import Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.config.storages import ForgetfulNodeStorage, NodeStorage, TemporaryFileBasedNodeStorage
from nucypher.network.nodes import Learner
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT

ADDITIONAL_NODES_TO_LEARN_ABOUT = 10
MOCK_URSULA_DB_FILEPATH = tempfile.mkdtemp()


class BaseTestNodeStorageBackends:

    @pytest.fixture(scope='class')
    def light_ursula(temp_dir_path):
        node = Ursula(rest_host=LOOPBACK_ADDRESS,
                      rest_port=MOCK_URSULA_STARTING_PORT,
                      db_filepath=MOCK_URSULA_DB_FILEPATH,
                      federated_only=True,
                      domain=TEMPORARY_DOMAIN)
        yield node

    character_class = Ursula
    federated_only = True
    storage_backend = NotImplemented

    def _read_and_write_metadata(self, ursula, node_storage):
        # Write Node
        node_storage.store_node_metadata(node=ursula)

        # Read Node
        node_from_storage = node_storage.get(checksum_address=ursula.checksum_address,
                                             federated_only=True)
        assert ursula == node_from_storage, "Node storage {} failed".format(node_storage)

        # Save more nodes
        all_known_nodes = set()
        for port in range(MOCK_URSULA_STARTING_PORT, MOCK_URSULA_STARTING_PORT + ADDITIONAL_NODES_TO_LEARN_ABOUT):
            node = Ursula(rest_host=LOOPBACK_ADDRESS,
                          db_filepath=MOCK_URSULA_DB_FILEPATH,
                          rest_port=port,
                          federated_only=True,
                          domain=TEMPORARY_DOMAIN)
            node_storage.store_node_metadata(node=node)
            all_known_nodes.add(node)

        # Read all nodes from storage
        all_stored_nodes = node_storage.all(federated_only=True)
        all_known_nodes.add(ursula)
        assert len(all_known_nodes) == len(all_stored_nodes) == 1 + ADDITIONAL_NODES_TO_LEARN_ABOUT

        known_checksums = sorted(n.checksum_address for n in all_known_nodes)
        stored_checksums = sorted(n.checksum_address for n in all_stored_nodes)

        assert known_checksums == stored_checksums

        # Read random nodes
        for i in range(3):
            random_node = all_known_nodes.pop()
            random_node_from_storage = node_storage.get(checksum_address=random_node.checksum_address,
                                                        federated_only=True)
            assert random_node.checksum_address == random_node_from_storage.checksum_address

        return True

    def _write_and_delete_metadata(self, ursula, node_storage):
        # Write Node
        node_storage.store_node_metadata(node=ursula)

        # Delete Node
        node_storage.remove(checksum_address=ursula.checksum_address, certificate=False)

        # Read Node
        with pytest.raises(NodeStorage.UnknownNode):
            _node_from_storage = node_storage.get(checksum_address=ursula.checksum_address,
                                                  federated_only=True)

        # Read all nodes from storage
        all_stored_nodes = node_storage.all(federated_only=True)
        assert all_stored_nodes == set()
        return True

    #
    # Storage Backend Tests
    #
    def test_delete_node_in_storage(self, light_ursula):
        assert self._write_and_delete_metadata(ursula=light_ursula, node_storage=self.storage_backend)

    def test_read_and_write_to_storage(self, light_ursula):
        assert self._read_and_write_metadata(ursula=light_ursula, node_storage=self.storage_backend)
        self.storage_backend.clear()


class TestInMemoryNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = ForgetfulNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                           federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()


class TestTemporaryFileBasedNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = TemporaryFileBasedNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                                    federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()

    def test_invalid_metadata(self, light_ursula):
        self._read_and_write_metadata(ursula=light_ursula, node_storage=self.storage_backend)
        some_node, another_node, *other = os.listdir(self.storage_backend.metadata_dir)

        # Let's break the metadata (but not the version)
        metadata_path = os.path.join(self.storage_backend.metadata_dir, some_node)
        with open(metadata_path, 'wb') as file:
            file.write(Learner.LEARNER_VERSION.to_bytes(4, 'big') + b'invalid')

        with pytest.raises(TemporaryFileBasedNodeStorage.InvalidNodeMetadata):
            self.storage_backend.get(checksum_address=some_node[:-5],
                                     federated_only=True,
                                     certificate_only=False)

        # Let's break the metadata, by putting a completely wrong version
        metadata_path = os.path.join(self.storage_backend.metadata_dir, another_node)
        with open(metadata_path, 'wb') as file:
            file.write(b'meh')  # Versions are expected to be 4 bytes, but this is 3 bytes

        with pytest.raises(TemporaryFileBasedNodeStorage.InvalidNodeMetadata):
            self.storage_backend.get(checksum_address=another_node[:-5],
                                     federated_only=True,
                                     certificate_only=False)

        # Since there are 2 broken metadata files, we should get 2 nodes less when reading all
        restored_nodes = self.storage_backend.all(federated_only=True, certificates_only=False)
        total_nodes = 1 + ADDITIONAL_NODES_TO_LEARN_ABOUT
        assert total_nodes - 2 == len(restored_nodes)
