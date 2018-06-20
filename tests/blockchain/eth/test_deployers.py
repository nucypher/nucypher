import pytest

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


def test_token_deployer_and_agent(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    # Trying to get token from blockchain before it's been published fails
    with pytest.raises(EthereumContractRegistry.UnknownContract):
        NucypherTokenAgent(blockchain=testerchain)

    # The big day...
    deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    # It's not armed
    with pytest.raises(NucypherTokenDeployer.ContractDeploymentError):
        deployer.deploy()

    # Token must be armed before deploying to the blockchain
    deployer.arm()
    deployer.deploy()

    # Create a token instance
    token_agent = deployer.make_agent()
    token_contract = testerchain.get_contract(token_agent.contract_address)
    expected_token_supply = token_contract.functions.totalSupply().call()
    assert expected_token_supply == token_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_token_agent = NucypherTokenAgent(blockchain=testerchain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__


@pytest.mark.slow()
def test_deploy_ethereum_contracts(testerchain):
    """
    Launch all ethereum contracts:
    - NuCypherToken
    - PolicyManager
    - MinersEscrow
    - UserEscrow
    - Issuer
    """
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()

    token_agent = NucypherTokenAgent(blockchain=testerchain)

    miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent, deployer_address=origin)
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()

    miner_agent = MinerAgent(token_agent=token_agent)

    policy_manager_contract = PolicyManagerDeployer(miner_agent=miner_agent, deployer_address=origin)
    policy_manager_contract.arm()
    policy_manager_contract.deploy()

    # TODO: Assert
