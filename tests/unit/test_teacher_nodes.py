import pytest

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.network.nodes import TEACHER_NODES


@pytest.fixture(autouse=True)
def mock_teacher_nodes(mocker):
    # override fixture
    yield


def test_default_teacher_seednodes_defined():
    for network_name in NetworksInventory.SUPPORTED_NETWORK_NAMES:
        if network_name == NetworksInventory.IBEX.name:
            # skip
            continue
        teacher_nodes = TEACHER_NODES[network_name]
        assert len(teacher_nodes) > 0
