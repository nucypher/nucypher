from nucypher.blockchain.eth.agents import PolicyManagerAgent, StakingEscrowAgent, AdjudicatorAgent, Agency
from nucypher.blockchain.eth.clients import Web3Client
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface, BlockchainInterface
from nucypher.cli.deploy import deploy
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI, MOCK_REGISTRY_FILEPATH


# def test_nucypher_deploy_status(click_runner,
#                                 testerchain,
#                                 agency):
#
#     # Simulate "Reconnection" within the CLI process to the testerchain
#     def connect(self, *args, **kwargs):
#         self._attach_provider(testerchain.provider)
#         self.w3 = self.Web3(provider=self._provider)
#         self.client = Web3Client.from_w3(w3=self.w3)
#     BlockchainDeployerInterface.connect = connect
#
#     status_command = ('status',
#                       '--provider-uri', TEST_PROVIDER_URI,
#                       '--poa')
#     result = click_runner.invoke(deploy, status_command, catch_exceptions=False)
#     assert result.exit_code == 0
#
#     staking_agent = StakingEscrowAgent(blockchain=testerchain)
#     policy_agent = PolicyManagerAgent(blockchain=testerchain)
#     adjudicator_agent = AdjudicatorAgent(blockchain=testerchain)
#
#     assert staking_agent.get_owner() in result.output
#     assert policy_agent.get_owner() in result.output
#     assert adjudicator_agent.get_owner() in result.output


def test_transfer_ownership(click_runner, testerchain, agency):

    # Simulate "Reconnection" within the CLI process to the testerchain
    def connect(self, *args, **kwargs):
        self._attach_provider(testerchain.provider)
        self.w3 = self.Web3(provider=self._provider)
        self.client = Web3Client.from_w3(w3=self.w3)
    BlockchainDeployerInterface.connect = connect
    BlockchainInterface.connect = connect

    maclane = testerchain.unassigned_accounts[0]
    ownership_command = ('transfer-ownership',
                         '--provider-uri', TEST_PROVIDER_URI,
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

    Agency.clear()

    staking_agent = StakingEscrowAgent(blockchain=testerchain)
    policy_agent = PolicyManagerAgent(blockchain=testerchain)
    adjudicator_agent = AdjudicatorAgent(blockchain=testerchain)

    assert staking_agent.get_owner() == testerchain.deployer_address
    assert policy_agent.get_owner() == testerchain.deployer_address
    assert adjudicator_agent.get_owner() == testerchain.deployer_address

    michwill = testerchain.unassigned_accounts[1]

    ownership_command = ('transfer-ownership',
                         '--deployer-address', testerchain.deployer_address,
                         '--contract-name', STAKING_ESCROW_CONTRACT_NAME,
                         '--registry-infile', MOCK_REGISTRY_FILEPATH,
                         '--provider-uri', TEST_PROVIDER_URI,
                         '--checksum-address', michwill,
                         '--poa')

    user_input = yes
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
    assert staking_agent.get_owner() == maclane
    assert staking_agent.get_owner() == michwill


def test_transfer_tokens(click_runner, testerchain, agency):

    maclane = testerchain.unassigned_accounts[0]

    ownership_command = ('transfer',
                         '--deployer-address', testerchain.deployer_address,
                         '--registry-infile', MOCK_REGISTRY_FILEPATH,
                         '--provider-uri', TEST_PROVIDER_URI,
                         '--target-address', maclane,
                         '--value', 100_000,
                         '--poa')

    user_input = 'Y\n'
    result = click_runner.invoke(deploy,
                                 ownership_command,
                                 input=user_input,
                                 catch_exceptions=False)
    assert result.exit_code == 0
