import pytest

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.config.storages import ForgetfulNodeStorage, TemporaryFileBasedNodeStorage
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.utils.ursula import select_test_port

ADDITIONAL_NODES_TO_LEARN_ABOUT = 10


def make_header(brand: bytes, major: int, minor: int) -> bytes:
    # Hardcoding this since it's too much trouble to expose it all the way from Rust
    assert len(brand) == 4
    major_bytes = major.to_bytes(2, 'big')
    minor_bytes = minor.to_bytes(2, 'big')
    header = brand + major_bytes + minor_bytes
    return header


class BaseTestNodeStorageBackends:

    character_class = Ursula
    storage_backend = NotImplemented

    def _read_and_write_metadata(self, ursula, node_storage, operator_addresses, signer):
        # Write Node
        node_storage.store_node_metadata(node=ursula)

        # Read Node
        node_from_storage = node_storage.get(stamp=ursula.stamp)
        assert ursula == node_from_storage, "Node storage {} failed".format(node_storage)

        pre_payment_method = SubscriptionManagerPayment(
            eth_provider=MOCK_ETH_PROVIDER_URI, network=TEMPORARY_DOMAIN
        )

        # Save more nodes
        all_known_nodes = set()
        for i in range(ADDITIONAL_NODES_TO_LEARN_ABOUT):
            node = Ursula(
                rest_host=LOOPBACK_ADDRESS,
                rest_port=select_test_port(),
                domain=TEMPORARY_DOMAIN,
                signer=signer,
                eth_endpoint=MOCK_ETH_PROVIDER_URI,
                polygon_endpoint=MOCK_ETH_PROVIDER_URI,
                checksum_address=operator_addresses[i],
                operator_address=operator_addresses[i],
                pre_payment_method=pre_payment_method,
            )
            node_storage.store_node_metadata(node=node)
            all_known_nodes.add(node)

        # Read all nodes from storage
        all_stored_nodes = node_storage.all()
        all_known_nodes.add(ursula)
        assert len(all_known_nodes) == len(all_stored_nodes) == 1 + ADDITIONAL_NODES_TO_LEARN_ABOUT

        known_checksums = sorted(n.checksum_address for n in all_known_nodes)
        stored_checksums = sorted(n.checksum_address for n in all_stored_nodes)

        assert known_checksums == stored_checksums

        # Read random nodes
        for i in range(3):
            random_node = all_known_nodes.pop()
            random_node_from_storage = node_storage.get(stamp=random_node.stamp)
            assert random_node.checksum_address == random_node_from_storage.checksum_address

        return True

    #
    # Storage Backend Tests
    #

    @pytest.mark.usefixtures("mock_registry_sources")
    def test_read_and_write_to_storage(self, light_ursula, testerchain):
        assert self._read_and_write_metadata(ursula=light_ursula,
                                             node_storage=self.storage_backend,
                                             operator_addresses=testerchain.ursulas_accounts,
                                             signer=Web3Signer(testerchain.client))
        self.storage_backend.clear()


class TestInMemoryNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = ForgetfulNodeStorage(character_class=BaseTestNodeStorageBackends.character_class)
    storage_backend.initialize()


class TestTemporaryFileBasedNodeStorage(BaseTestNodeStorageBackends):
    storage_backend = TemporaryFileBasedNodeStorage(character_class=BaseTestNodeStorageBackends.character_class)
    storage_backend.initialize()

    def test_invalid_metadata(self, light_ursula, testerchain):
        self._read_and_write_metadata(ursula=light_ursula, node_storage=self.storage_backend, operator_addresses=testerchain.ursulas_accounts, signer=Web3Signer(testerchain.client))
        some_node, another_node, *other = list(self.storage_backend.metadata_dir.iterdir())

        # Let's break the metadata (but not the version)
        metadata_path = self.storage_backend.metadata_dir / some_node
        with open(metadata_path, 'wb') as file:
            file.write(make_header(b'NdMd', 1, 0) + b'invalid')

        with pytest.raises(TemporaryFileBasedNodeStorage.InvalidNodeMetadata):
            self.storage_backend.get(stamp=some_node.name[:-5], certificate_only=False)

        # Let's break the metadata, by putting a completely wrong version
        metadata_path = self.storage_backend.metadata_dir / another_node
        with open(metadata_path, 'wb') as file:
            full_header = make_header(b'NdMd', 1, 0)
            file.write(full_header[:-1])  # Not even a valid header

        with pytest.raises(TemporaryFileBasedNodeStorage.InvalidNodeMetadata):
            self.storage_backend.get(stamp=another_node.name[:-5], certificate_only=False)

        # Since there are 2 broken metadata files, we should get 2 nodes less when reading all
        restored_nodes = self.storage_backend.all(certificates_only=False)
        total_nodes = 1 + ADDITIONAL_NODES_TO_LEARN_ABOUT
        assert total_nodes - 2 == len(restored_nodes)
