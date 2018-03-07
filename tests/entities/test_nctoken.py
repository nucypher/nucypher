from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.agents import NuCypherKMSTokenAgent
from nkms_eth.deployers import NuCypherKMSTokenDeployer


def test_deploy_and_fetch_nucypherkms_token(testerchain):

    # Trying to get token from blockchain before it's been published fails
    with raises(NoKnownAddress):
        NuCypherKMSTokenAgent(blockchain=testerchain)

    # The big day...
    deployer = NuCypherKMSTokenDeployer(blockchain=testerchain)

    with raises(NuCypherKMSTokenDeployer.ContractDeploymentError):
        deployer.deploy()

    # Token must be armed before deploying to the blockchain
    deployer.arm()
    deployer.deploy()

    # Create a token instance
    token_agent = NuCypherKMSTokenAgent(blockchain=testerchain)

    # Make sure we got the name right
    deployer_contract_identifier = NuCypherKMSTokenDeployer.contract_name
    contract_identifier = NuCypherKMSTokenAgent._contract_name
    assert'NuCypherKMSToken' == contract_identifier == deployer_contract_identifier

    # Ensure the contract is deployed and has a valid blockchain address
    assert len(token_agent.contract_address) == 42

    # Check that the token contract has tokens
    assert token_agent.call().totalSupply() != 0
    # assert token().totalSupply() == 10 ** 9 - 1    # TODO

    # Retrieve the token from the blockchain
    same_token_agent = NuCypherKMSTokenAgent(blockchain=testerchain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__
