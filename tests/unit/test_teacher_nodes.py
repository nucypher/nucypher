import pytest

from nucypher.blockchain.eth import domains
from nucypher.network.nodes import TEACHER_NODES


@pytest.fixture(autouse=True)
def mock_teacher_nodes(mocker):
    # override fixture which mocks TEACHER_NODES
    yield


@pytest.fixture(scope="module")
def test_registry(module_mocker):
    # override fixture which mocks SUPPORTED_DOMAIN_NAMES
    yield


def test_default_teacher_seednodes_defined():
    for domain in domains.SUPPORTED_DOMAIN_NAMES:
        teacher_nodes = TEACHER_NODES[domain]
        assert len(teacher_nodes) > 0
