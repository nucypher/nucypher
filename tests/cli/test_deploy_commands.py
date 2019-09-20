import pytest

from nucypher.blockchain.eth.agents import (
    PolicyManagerAgent,
    StakingEscrowAgent,
    AdjudicatorAgent,
    ContractAgency
)
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import StakingEscrowDeployer
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.cli.deploy import deploy
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI, MOCK_REGISTRY_FILEPATH, \
    INSECURE_DEVELOPMENT_PASSWORD, INSECURE_DEPLOYMENT_SECRET_PLAINTEXT

registry_filepath = '/tmp/nucypher-test-registry.json'


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    test_registry.commit(filepath=registry_filepath, overwrite=True)


def test_nucypher_deploy_inspect_no_deployments(click_runner, testerchain):

    status_command = ('inspect',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', registry_filepath,
                      '--poa')

    result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
    assert result.exit_code == 0


def test_nucypher_deploy_inspect_fully_deployed(click_runner, testerchain, agency):

    local_registry = LocalContractRegistry(filepath=registry_filepath)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=local_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=local_registry)

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


def test_transfer_ownership(click_runner, testerchain, agency):

    local_registry = LocalContractRegistry(filepath=registry_filepath)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=local_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=local_registry)

    assert staking_agent.owner == testerchain.etherbase_account
    assert policy_agent.owner == testerchain.etherbase_account
    assert adjudicator_agent.owner == testerchain.etherbase_account

    maclane = testerchain.unassigned_accounts[0]

    ownership_command = ('transfer-ownership',
                         '--registry-infile', registry_filepath,
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


def test_bare_contract_deployment(click_runner, test_registry):

    command = ('contracts',
               '--contract-name', StakingEscrowDeployer.contract_name,
               '--bare',
               '--provider', TEST_PROVIDER_URI,
               '--registry-outfile', registry_filepath,
               '--poa')

    user_input = '0\n' + 'Y\n' + 'DEPLOY'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0


def test_manual_proxy_retargeting(testerchain, click_runner, test_registry, token_economics):
    local_registry = LocalContractRegistry(filepath=registry_filepath)
    deployer = StakingEscrowDeployer(deployer_address=testerchain.etherbase_account,
                                     registry=local_registry,
                                     economics=token_economics)

    untargeted_deployment = deployer.get_latest_enrollment(registry=local_registry)
    command = ('upgrade',
               '--retarget',
               '--contract-name', StakingEscrowDeployer.contract_name,
               '--target-address', untargeted_deployment.address,
               '--provider', TEST_PROVIDER_URI,
               '--registry-infile', registry_filepath,
               '--registry-outfile', registry_filepath,
               '--poa')

    old_secret = INSECURE_DEPLOYMENT_SECRET_PLAINTEXT.decode()
    user_input = '0\n' + 'Y\n' + f'{old_secret}\n' + (f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2) + 'Y\n'
    result = click_runner.invoke(deploy, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
