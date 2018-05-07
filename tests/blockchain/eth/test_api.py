import pytest

from nkms.blockchain.eth.agents import NuCypherKMSTokenAgent, MinerAgent
from nkms.blockchain.eth.deployers import NuCypherKMSTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer


def test_token_deployer_and_agent(chain):

    # Trying to get token from blockchain before it's been published fails
    # with raises(NoKnownAddress):
    #     NuCypherKMSTokenAgent(blockchain=chain)

    # The big day...
    deployer = NuCypherKMSTokenDeployer(blockchain=chain)

    with pytest.raises(NuCypherKMSTokenDeployer.ContractDeploymentError):
        deployer.deploy()

    # Token must be armed before deploying to the blockchain
    deployer.arm()
    deployer.deploy()

    # Create a token instance
    token_agent = NuCypherKMSTokenAgent(blockchain=chain)

    # Make sure we got the name right
    deployer_contract_identifier = NuCypherKMSTokenDeployer._contract_name
    assert'NuCypherKMSToken' == deployer_contract_identifier

    # Ensure the contract is deployed and has a valid blockchain address
    assert len(token_agent.contract_address) == 42

    # Check that the token contract has tokens
    assert token_agent.read().totalSupply() != 0
    # assert token().totalSupply() == int(1e9) * _M     # TODO

    # Retrieve the token from the blockchain
    same_token_agent = NuCypherKMSTokenAgent(blockchain=chain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__


@pytest.mark.slow
def test_deploy_ethereum_contracts(chain):
    """
    Launch all ethereum contracts:
    - NuCypherKMSToken
    - PolicyManager
    - MinersEscrow
    - UserEscrow
    - Issuer
    """

    token_deployer = NuCypherKMSTokenDeployer(blockchain=chain)
    token_deployer.arm()
    token_deployer.deploy()

    token_agent = NuCypherKMSTokenAgent(blockchain=chain)

    miner_escrow_deployer = MinerEscrowDeployer(token_agent=token_agent)
    miner_escrow_deployer.arm()
    miner_escrow_deployer.deploy()

    miner_agent = MinerAgent(token_agent=token_agent)

    policy_manager_contract = PolicyManagerDeployer(miner_agent=miner_agent)
    policy_manager_contract.arm()
    policy_manager_contract.deploy()
