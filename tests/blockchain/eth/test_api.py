import pytest
from pytest import raises

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer
from nucypher.blockchain.eth.interfaces import Registrar


def test_token_deployer_and_agent(chain):

    # Trying to get token from blockchain before it's been published fails
    with pytest.raises(Registrar.UnknownContract):
        NucypherTokenAgent(blockchain=chain)

    # The big day...
    deployer = NucypherTokenDeployer(blockchain=chain)

    with pytest.raises(NucypherTokenDeployer.ContractDeploymentError):
        deployer.deploy()

    # Token must be armed before deploying to the blockchain
    deployer.arm()
    deployer.deploy()

    # Create a token instance
    token_agent = NucypherTokenAgent(blockchain=chain)

    # Make sure we got the name right
    deployer_contract_identifier = NucypherTokenDeployer._contract_name
    assert'NuCypherToken' == deployer_contract_identifier

    # Ensure the contract is deployed and has a valid blockchain address
    assert len(token_agent.contract_address) == 42

    # Check that the token contract has tokens
    assert token_agent.contract.functions.totalSupply().call() != 0
    # assert token().totalSupply() == int(1e9) * _M     # TODO

    # Retrieve the token from the blockchain
    same_token_agent = NucypherTokenAgent(blockchain=chain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__


@pytest.mark.slow()
def test_deploy_ethereum_contracts(chain):
    """
    Launch all ethereum contracts:
    - NuCypherToken
    - PolicyManager
    - MinersEscrow
    - UserEscrow
    - Issuer
    """

    token_deployer = NucypherTokenDeployer(blockchain=chain)
    token_deployer.arm()
    token_deployer.deploy()

    token_agent = NucypherTokenAgent(blockchain=chain)

    miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent)
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()

    miner_agent = MinerAgent(token_agent=token_agent)

    policy_manager_contract = PolicyManagerDeployer(miner_agent=miner_agent)
    policy_manager_contract.arm()
    policy_manager_contract.deploy()
