import pytest

from nucypher.blockchain.eth import domains
from nucypher.network.nodes import TEACHER_NODES


@pytest.fixture(autouse=True)
def mock_peers(mocker):
    # override fixture which mocks TEACHER_NODES
    yield


@pytest.fixture(scope="module")
def test_registry(module_mocker):
    # override fixture which mocks domains.SUPPORTED_DOMAINS
    yield


def test_default_peer_seednodes_defined():
    for name, domain in domains.SUPPORTED_DOMAINS.items():
        peers = TEACHER_NODES[domain]
        assert len(peers) > 0
