from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.token import NuCypherKMSTokenAgent


def test_launch_and_fetch_nucypherkms_token(testerchain):

    # Trying to get token from blockchain before it's been published fails
    with raises(NoKnownAddress):
        NuCypherKMSTokenAgent.get(blockchain=testerchain)

    # Create a token instance
    token = NuCypherKMSTokenAgent(blockchain=testerchain)

    # Make sure we got the name right
    contract_identifier = NuCypherKMSTokenAgent._NuCypherKMSToken__contract_name
    assert'NuCypherKMSToken' == contract_identifier

    # The big day...
    with raises(NuCypherKMSTokenAgent.ContractDeploymentError):
        token.deploy()

    # Token must be armed before deploying to the blockchain
    token.arm()
    token.deploy()

    # Ensure the contract is deployed and has a valid blockchain address
    assert len(token._contract.address) == 42

    # Check that the token contract has tokens
    assert token().totalSupply() != 0
    # assert token().totalSupply() == 10 ** 9 - 1    # TODO

    # Retrieve the token from the blockchain
    same_token = NuCypherKMSTokenAgent.get(blockchain=testerchain)

    # Compare the contract address for equality
    assert token._contract.address == same_token._contract.address
    assert token == same_token  # __eq__
