import pytest

from nucypher.blockchain.eth import domains
from nucypher.network.nodes import TEACHER_NODES


@pytest.fixture(autouse=True)
def mock_teacher_nodes(mocker):
    # override fixture
    yield


def test_default_teacher_seednodes_defined():
    for domain in domains.SUPPORTED_DOMAIN_NAMES:
        teacher_nodes = TEACHER_NODES[domain]
        assert len(teacher_nodes) > 0
