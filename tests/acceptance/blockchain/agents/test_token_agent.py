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
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope='module')
def agent(testerchain, test_registry) -> NucypherTokenAgent:
    origin, *everybody_else = testerchain.client.accounts
    token_deployer = NucypherTokenDeployer(registry=test_registry, deployer_address=origin)

    token_deployer.deploy()
    token_agent = token_deployer.make_agent()
    return token_agent


def test_token_properties(agent):
    testerchain = agent.blockchain

    # Internal
    assert 'NuCypher' == agent.contract.functions.name().call()
    assert 18 == agent.contract.functions.decimals().call()
    assert 'NU' == agent.contract.functions.symbol().call()

    # Cannot transfer any ETH to token contract
    with pytest.raises((TransactionFailed, ValueError)):
        origin = testerchain.client.coinbase
        payload = {'from': origin, 'to': agent.contract_address, 'value': 1}
        tx = testerchain.client.send_transaction(payload)
        testerchain.wait_for_receipt(tx)

    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == NucypherTokenAgent.contract_name
    assert not agent._proxy_name  # not upgradeable


def test_get_balance(agent, token_economics):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts
    balance = agent.get_balance(address=someone)
    assert balance == 0
    balance = agent.get_balance(address=deployer)
    assert balance == token_economics.erc20_total_supply


def test_approve_transfer(agent, token_economics, mock_transacting_power_activation):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts

    mock_transacting_power_activation(account=someone, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Approve
    receipt = agent.approve_transfer(amount=token_economics.minimum_allowed_locked,
                                     spender_address=agent.contract_address,
                                     sender_address=someone)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


def test_transfer(agent, token_economics, mock_transacting_power_activation):
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.client.accounts

    mock_transacting_power_activation(account=origin, password=INSECURE_DEVELOPMENT_PASSWORD)

    old_balance = agent.get_balance(someone)
    receipt = agent.transfer(amount=token_economics.minimum_allowed_locked,
                             target_address=someone,
                             sender_address=origin)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    new_balance = agent.get_balance(someone)
    assert new_balance == old_balance + token_economics.minimum_allowed_locked


def test_approve_and_call(agent, token_economics, mock_transacting_power_activation, deploy_contract):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts

    mock_target, _ = deploy_contract('ReceiveApprovalMethodMock')

    mock_transacting_power_activation(account=someone, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Approve and call
    call_data = b"Good morning, that's a nice tnetennba."
    receipt = agent.approve_and_call(amount=token_economics.minimum_allowed_locked,
                                     target_address=mock_target.address,
                                     sender_address=someone,
                                     call_data=call_data)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    assert mock_target.functions.extraData().call() == call_data
    assert mock_target.functions.sender().call() == someone
    assert mock_target.functions.value().call() == token_economics.minimum_allowed_locked
