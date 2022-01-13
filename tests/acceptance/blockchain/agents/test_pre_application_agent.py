
import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent, PREApplicationAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, PREApplicationDeployer
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower

MIN_AUTHORIZATION = 1
MIN_SECONDS = 1


@pytest.fixture(scope='module')
def agent(testerchain, test_registry, deploy_contract) -> PREApplicationAgent:
    origin, *everybody_else = testerchain.client.accounts

    # faked threshold staking interface
    threshold_staking, _ = deploy_contract('TStakingTest')

    deployer = PREApplicationDeployer(
        registry=test_registry,
        min_seconds=MIN_SECONDS,
        min_authorization=MIN_AUTHORIZATION,
        staking_interface=threshold_staking.address,
    )
    power = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))
    deployer.deploy(transacting_power=power)
    _agent = deployer.make_agent()
    return _agent


def test_get_min_authorization(agent):
    result = agent.get_min_authorization()
    assert result == MIN_AUTHORIZATION


def test_get_min_seconds(agent):
    result = agent.get_min_worker_seconds()
    assert result == MIN_SECONDS
