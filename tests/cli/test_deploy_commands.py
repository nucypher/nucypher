import pytest

from nucypher.blockchain.eth.agents import PolicyManagerAgent, StakingEscrowAgent, AdjudicatorAgent, NucypherTokenAgent, \
    ContractAgency
from nucypher.blockchain.eth.clients import Web3Client
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterface
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.cli.deploy import deploy
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI

registry_filepath = '/tmp/nucypher-test-registry.json'


@pytest.fixture(scope='module', autouse=True)
def mocked_blockchain_connection(testerchain, agency):

    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    testerchain.registry.commit(filepath=registry_filepath)

    # Simulate "Reconnection" within the CLI process to the testerchain
    def connect(self, *args, **kwargs):
        self._attach_provider(testerchain.provider)
        self.w3 = self.Web3(provider=self._provider)
        self.client = Web3Client.from_w3(w3=self.w3)
    BlockchainInterface.connect = connect
    BlockchainDeployerInterface.connect = connect


def test_nucypher_deploy_status_no_deployments(click_runner, testerchain):

    status_command = ('status',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', registry_filepath,
                      '--poa')

    result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
    assert result.exit_code == 0


def test_nucypher_deploy_status_fully_deployed(click_runner, testerchain, test_registry, agency):

    status_command = ('status',
                      '--provider', TEST_PROVIDER_URI,
                      '--registry-infile', registry_filepath,
                      '--poa')

    result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=test_registry)

    assert staking_agent.get_owner() in result.output
    assert policy_agent.get_owner() in result.output
    assert adjudicator_agent.get_owner() in result.output


def test_transfer_ownership(click_runner, testerchain, agency):

    maclane = testerchain.unassigned_accounts[0]
    michwill = testerchain.unassigned_accounts[1]

    ownership_command = ('transfer-ownership',
                         '--provider', TEST_PROVIDER_URI,
                         '--registry-infile', registry_filepath,
                         '--target-address', maclane,
                         '--poa')

    account_index = '0\n'
    yes = 'Y\n'
    user_input = account_index + yes
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    staking_agent = StakingEscrowAgent(blockchain=testerchain)
    policy_agent = PolicyManagerAgent(blockchain=testerchain)
    adjudicator_agent = AdjudicatorAgent(blockchain=testerchain)

    assert staking_agent.get_owner() == maclane
    assert policy_agent.get_owner() == maclane
    assert adjudicator_agent.get_owner() == maclane

    ownership_command = ('transfer-ownership',
                         '--deployer-address', maclane,
                         '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
                         '--registry-infile', registry_filepath,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', michwill,
                         '--poa')

    user_input = yes
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.get_owner() == michwill


def test_transfer_tokens(click_runner, testerchain, agency):

    token_agent = NucypherTokenAgent(blockchain=testerchain)

    maclane = testerchain.unassigned_accounts[0]
    pre_transfer_balance = token_agent.get_balance(address=maclane)

    ownership_command = ('transfer-tokens',
                         '--deployer-address', testerchain.deployer_address,
                         '--registry-infile', registry_filepath,
                         '--provider', TEST_PROVIDER_URI,
                         '--target-address', maclane,
                         '--value', 100_000,
                         '--poa')

    user_input = 'Y\n'
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0

    # Check post-transfer balance
    assert token_agent.get_balance(address=maclane) == pre_transfer_balance + 100_000
