import pytest

from nucypher.blockchain.eth.agents import (
    PolicyManagerAgent,
    StakingEscrowAgent,
    AdjudicatorAgent,
    ContractAgency
)
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.cli.deploy import deploy
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI, MOCK_REGISTRY_FILEPATH

registry_filepath = '/tmp/nucypher-test-registry.json'


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    test_registry.commit(filepath=registry_filepath)


def test_nucypher_deploy_inspect_no_deployments(click_runner, testerchain):

    status_command = ('inspect',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', registry_filepath,
                      '--poa')

    result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
    assert result.exit_code == 0


def test_nucypher_deploy_inspect_fully_deployed(click_runner, testerchain, test_registry, agency):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=test_registry)

    status_command = ('inspect',
                      '--registry-infile', MOCK_REGISTRY_FILEPATH,
                      '--provider', TEST_PROVIDER_URI,
                      '--poa')

    result = click_runner.invoke(deploy,
                                 status_command,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.owner in result.output
    assert policy_agent.owner in result.output
    assert adjudicator_agent.owner in result.output


def test_transfer_ownership(click_runner, testerchain, test_registry, agency):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=test_registry)

    assert staking_agent.owner == testerchain.etherbase_account
    assert policy_agent.owner == testerchain.etherbase_account
    assert adjudicator_agent.owner == testerchain.etherbase_account

    maclane = testerchain.unassigned_accounts[0]

    ownership_command = ('transfer-ownership',
                         '--registry-infile', MOCK_REGISTRY_FILEPATH,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', maclane,
                         '--poa')

    account_index = '0\n'
    yes = 'Y\n'
    user_input = account_index + yes + yes

    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    assert staking_agent.owner == maclane
    assert policy_agent.owner == maclane
    assert adjudicator_agent.owner == maclane

    michwill = testerchain.unassigned_accounts[1]

    ownership_command = ('transfer-ownership',
                         '--deployer-address', maclane,
                         '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
                         '--registry-infile', MOCK_REGISTRY_FILEPATH,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', michwill,
                         '--poa')

    user_input = yes
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.owner != maclane
    assert staking_agent.owner == michwill
