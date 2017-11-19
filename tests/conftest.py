import pytest
from nkms_eth import blockchain


@pytest.fixture()
def project():
    return blockchain.project()


@pytest.fixture()
def chain():
    blockchain.DEFAULT_NETWORK = 'tester'
    yield blockchain.chain()
    blockchain.disconnect()
