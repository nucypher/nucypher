"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import pytest
from web3.contract import Contract

from tests.constants import (
    TEST_PROVIDER_URI,
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


@pytest.fixture(scope='module')
def test_registry():
    registry = InMemoryContractRegistry()
    return registry


@pytest.fixture()
def ursula_decentralized_test_config(testerchain, test_registry):
    config = make_ursula_test_configuration(federated=False,
                                            provider_uri=TEST_PROVIDER_URI,
                                            test_registry=test_registry,
                                            rest_port=MOCK_URSULA_STARTING_PORT)

    return config
