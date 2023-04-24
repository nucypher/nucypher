import pytest

from nucypher.blockchain.eth.clients import EthereumClient


@pytest.fixture(scope="function")
def mock_funding_and_bonding(testerchain, mocker):
    mocker.patch(
        "nucypher.blockchain.eth.actors.Operator.get_staking_provider_address",
        return_value=testerchain.stake_providers_accounts[0],
    )
    mocker.patch.object(EthereumClient, "get_balance", return_value=1)
