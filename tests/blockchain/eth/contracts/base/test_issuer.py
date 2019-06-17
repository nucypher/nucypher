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
import os

import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract

SECRET_LENGTH = 32


@pytest.fixture()
def token(testerchain):
    # Create an ERC20 token
    token, _ = testerchain.deploy_contract('NuCypherToken', 2 * 10 ** 40)
    return token


@pytest.mark.slow
def test_issuer(testerchain, token):
    creator = testerchain.w3.eth.accounts[0]
    ursula = testerchain.w3.eth.accounts[1]

    # Only token contract is allowed in Issuer constructor
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('IssuerMock', ursula, 1, 10 ** 43, 10 ** 4, 10 ** 4)

    # Creator deploys the issuer
    issuer, _ = testerchain.deploy_contract('IssuerMock', token.address, 1, 10 ** 43, 10 ** 4, 10 ** 4)
    events = issuer.events.Initialized.createFilter(fromBlock='latest')

    # Give staker tokens for reward and initialize contract
    reserved_reward = 2 * 10 ** 40 - 10 ** 30
    tx = token.functions.transfer(issuer.address, reserved_reward).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Only owner can initialize
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.initialize().transact({'from': ursula})
        testerchain.wait_for_receipt(tx)
    tx = issuer.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    events = events.get_all_entries()
    assert 1 == len(events)
    assert reserved_reward == events[0]['args']['reservedReward']
    balance = token.functions.balanceOf(issuer.address).call()

    # Can't initialize second time
    with pytest.raises((TransactionFailed, ValueError)):
        tx = issuer.functions.initialize().transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Check result of minting tokens
    tx = issuer.functions.testMint(0, 1000, 2000, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 10 == token.functions.balanceOf(ursula).call()
    assert balance - 10 == token.functions.balanceOf(issuer.address).call()

    # The result must be more because of a different proportion of lockedValue and totalLockedValue
    tx = issuer.functions.testMint(0, 500, 500, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 30 == token.functions.balanceOf(ursula).call()
    assert balance - 30 == token.functions.balanceOf(issuer.address).call()

    # The result must be more because of bigger value of allLockedPeriods
    tx = issuer.functions.testMint(0, 500, 500, 10 ** 4).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 70 == token.functions.balanceOf(ursula).call()
    assert balance - 70 == token.functions.balanceOf(issuer.address).call()

    # The result is the same because allLockedPeriods more then specified coefficient _rewardedPeriods
    tx = issuer.functions.testMint(0, 500, 500, 2 * 10 ** 4).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 110 == token.functions.balanceOf(ursula).call()
    assert balance - 110 == token.functions.balanceOf(issuer.address).call()


@pytest.mark.slow
def test_inflation_rate(testerchain, token):
    """
    Check decreasing of inflation rate after minting.
    During one period inflation rate must be the same
    """

    creator = testerchain.w3.eth.accounts[0]
    ursula = testerchain.w3.eth.accounts[1]

    # Creator deploys the contract
    issuer, _ = testerchain.deploy_contract('IssuerMock', token.address, 1, 2 * 10 ** 19, 1, 1)

    # Give staker tokens for reward and initialize contract
    tx = token.functions.transfer(issuer.address, 2 * 10 ** 40 - 10 ** 30).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = issuer.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    reward = issuer.functions.getReservedReward().call()

    # Mint some tokens and save result of minting
    period = issuer.functions.getCurrentPeriod().call()
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    one_period = token.functions.balanceOf(ursula).call()

    # Mint more tokens in the same period, inflation rate must be the same as in previous minting
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period == token.functions.balanceOf(ursula).call()
    assert reward - token.functions.balanceOf(ursula).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period, inflation rate must be lower than in previous minting
    tx = issuer.functions.testMint(period + 2, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 3 * one_period > token.functions.balanceOf(ursula).call()
    assert reward - token.functions.balanceOf(ursula).call() == issuer.functions.getReservedReward().call()
    minted_amount = token.functions.balanceOf(ursula).call() - 2 * one_period

    # Mint tokens in the first period again, inflation rate must be the same as in previous minting
    # but can't be equals as in first minting because rate can't be increased
    tx = issuer.functions.testMint(period + 1, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period + 2 * minted_amount == token.functions.balanceOf(ursula).call()
    assert reward - token.functions.balanceOf(ursula).call() == issuer.functions.getReservedReward().call()

    # Mint tokens in the next period, inflation rate must be lower than in previous minting
    tx = issuer.functions.testMint(period + 3, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 2 * one_period + 3 * minted_amount > token.functions.balanceOf(ursula).call()
    assert reward - token.functions.balanceOf(ursula).call() == issuer.functions.getReservedReward().call()

    # Return some tokens as a reward
    balance = token.functions.balanceOf(ursula).call()
    reward = issuer.functions.getReservedReward().call()
    tx = issuer.functions.testUnMint(2 * one_period + 2 * minted_amount).transact()
    testerchain.wait_for_receipt(tx)
    assert reward + 2 * one_period + 2 * minted_amount == issuer.functions.getReservedReward().call()

    # Rate will be increased because some tokens were returned
    tx = issuer.functions.testMint(period + 3, 1, 1, 0).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert balance + one_period == token.functions.balanceOf(ursula).call()
    assert reward + one_period + 2 * minted_amount == issuer.functions.getReservedReward().call()


@pytest.mark.slow
def test_upgrading(testerchain, token):
    creator = testerchain.w3.eth.accounts[0]

    secret = os.urandom(SECRET_LENGTH)
    secret_hash = testerchain.w3.keccak(secret)
    secret2 = os.urandom(SECRET_LENGTH)
    secret2_hash = testerchain.w3.keccak(secret2)

    # Deploy contract
    contract_library_v1, _ = testerchain.deploy_contract('Issuer', token.address, 1, 1, 1, 1)
    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract_library_v1.address, secret_hash)

    # Deploy second version of the contract
    contract_library_v2, _ = testerchain.deploy_contract('IssuerV2Mock', token.address, 2, 2, 2, 2)
    contract = testerchain.w3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Give tokens for reward and initialize contract
    tx = token.functions.transfer(contract.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = contract.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Upgrade to the second version, check new and old values of variables
    period = contract.functions.currentMintingPeriod().call()
    assert 1 == contract.functions.miningCoefficient().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert 2 == contract.functions.miningCoefficient().call()
    assert 2 * 3600 == contract.functions.secondsPerPeriod().call()
    assert 2 == contract.functions.lockedPeriodsCoefficient().call()
    assert 2 == contract.functions.rewardedPeriods().call()
    assert period == contract.functions.currentMintingPeriod().call()
    assert 2 * 10 ** 40 == contract.functions.totalSupply().call()
    # Check method from new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = testerchain.deploy_contract('IssuerBad', token.address, 2, 2, 2, 2)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret2, secret_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback(secret2, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check old values
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert 1 == contract.functions.miningCoefficient().call()
    assert 3600 == contract.functions.secondsPerPeriod().call()
    assert 1 == contract.functions.lockedPeriodsCoefficient().call()
    assert 1 == contract.functions.rewardedPeriods().call()
    assert period == contract.functions.currentMintingPeriod().call()
    assert 2 * 10 ** 40 == contract.functions.totalSupply().call()
    # After rollback can't use new ABI
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret, secret2_hash)\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert 4 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert 3 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
