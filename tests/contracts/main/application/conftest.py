


import pytest
from web3.contract import Contract

from tests.constants import (
    TEST_ETH_PROVIDER_URI,
)
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT
from tests.utils.config import make_ursula_test_configuration
from nucypher.blockchain.eth.registry import InMemoryContractRegistry

# @pytest.fixture()
# def token(deploy_contract, token_economics):
#     # Create an ERC20 token
#     token, _ = deploy_contract('TToken', _totalSupplyOfTokens=token_economics.erc20_total_supply)
#     return token


@pytest.fixture()
def threshold_staking(deploy_contract):
    threshold_staking, _ = deploy_contract('ThresholdStakingForPREApplicationMock')
    return threshold_staking


@pytest.fixture()
def pre_application(testerchain, threshold_staking, deploy_contract, application_economics):
    min_authorization = application_economics.min_authorization
    min_operator_seconds = application_economics.min_operator_seconds

    # Creator deploys the PRE application
    contract, _ = deploy_contract(
        'SimplePREApplication',
        threshold_staking.address,
        min_authorization,
        min_operator_seconds
    )

    tx = threshold_staking.functions.setApplication(contract.address).transact()
    testerchain.wait_for_receipt(tx)

    return contract
