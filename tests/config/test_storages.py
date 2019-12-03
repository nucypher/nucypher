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

from nucypher.characters.lawful import Ursula
from nucypher.storage.node import (
    ForgetfulNodeStorage,
    TemporaryFileBasedNodeStorage,
    NodeStorage)
from nucypher.utilities.sandbox.constants import (
    MOCK_URSULA_DB_FILEPATH,
    MOCK_URSULA_STARTING_PORT)


class BaseTestNodeStorageBackends:

    @pytest.fixture(scope='class')
    def light_ursula(temp_dir_path):
        node = Ursula(rest_host='127.0.0.1',
                      rest_port=MOCK_URSULA_STARTING_PORT,
                      db_filepath=MOCK_URSULA_DB_FILEPATH,
                      federated_only=True)
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
        for port in range(MOCK_URSULA_STARTING_PORT, MOCK_URSULA_STARTING_PORT+100):
            node = Ursula(rest_host='127.0.0.1', db_filepath=MOCK_URSULA_DB_FILEPATH, rest_port=port,
                          federated_only=True)
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


class TestInMemoryNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = ForgetfulNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                           federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()


class TestTemporaryFileBasedNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = TemporaryFileBasedNodeStorage(character_class=BaseTestNodeStorageBackends.character_class,
                                                    federated_only=BaseTestNodeStorageBackends.federated_only)
    storage_backend.initialize()
