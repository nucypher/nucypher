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
from web3.contract import Contract


@pytest.fixture()
def preallocation_escrow(testerchain, router, deploy_contract):
    creator = testerchain.client.accounts[0]
    user = testerchain.client.accounts[1]

    contract, _ = deploy_contract('PreallocationEscrow', router.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def preallocation_escrow_interface(testerchain, staking_interface, preallocation_escrow):
    return testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=preallocation_escrow.address,
        ContractFactoryClass=Contract)


def test_escrow(testerchain, token, preallocation_escrow, preallocation_escrow_interface, escrow):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    deposits = preallocation_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the preallocation escrow and lock them
    tx = token.functions.approve(preallocation_escrow.address, 2000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check locked tokens
    assert 1000 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert owner == preallocation_escrow.functions.owner().call()
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    events = deposits.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert creator == event_args['sender']
    assert 1000 == event_args['value']
    assert 1000 == event_args['duration']

    # Can't deposit tokens again, only once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.initialDeposit(1000, 1000).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Transfer more tokens without locking
    tx = token.functions.transfer(preallocation_escrow.address, 300).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 1300 == token.functions.balanceOf(preallocation_escrow.address).call()
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    withdraws = preallocation_escrow.events.TokensWithdrawn.createFilter(fromBlock='latest')

    # Only owner can withdraw available tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(1).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow.functions.withdrawTokens(300).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 300 == token.functions.balanceOf(owner).call()
    assert 1000 == token.functions.balanceOf(preallocation_escrow.address).call()

    events = withdraws.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['owner']
    assert 300 == event_args['value']

    # Wait some time
    testerchain.time_travel(seconds=500)
    # Tokens are still locked
    assert 1000 == preallocation_escrow.functions.getLockedTokens().call()

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    assert 300 == token.functions.balanceOf(owner).call()

    # Owner can stake tokens

    tx = preallocation_escrow_interface.functions.depositAsStaker(100, 5).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(preallocation_escrow.address).call() == 900
    assert preallocation_escrow.functions.getLockedTokens().call() == 1000
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Only owner can deposit tokens to the staker escrow
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow_interface.functions.depositAsStaker(100, 5).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Give some tokens as a reward and withdraw equal amount from contract
    tx = token.functions.approve(escrow.address, 100).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(preallocation_escrow.address, 100, 0).transact()
    testerchain.wait_for_receipt(tx)

    # Can't withdraw more than reward
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(101).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    tx = preallocation_escrow.functions.withdrawTokens(100).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(owner).call() == 400
    assert token.functions.balanceOf(preallocation_escrow.address).call() == 800
    assert preallocation_escrow.functions.getLockedTokens().call() == 1000

    events = withdraws.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['owner'] == owner
    assert event_args['value'] == 100

    # Can't withdraw before unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    tx = preallocation_escrow_interface.functions.withdrawAsStaker(100).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(preallocation_escrow.address).call() == 900
    assert preallocation_escrow.functions.getLockedTokens().call() == 1000
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawTokens(1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Wait more time and withdraw all after unlocking
    testerchain.time_travel(seconds=500)
    assert preallocation_escrow.functions.getLockedTokens().call() == 0
    tx = preallocation_escrow.functions.withdrawTokens(900).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(preallocation_escrow.address).call() == 0
    assert token.functions.balanceOf(owner).call() == 1300

    events = withdraws.get_all_entries()
    assert len(events) == 3
    event_args = events[-1]['args']
    assert event_args['owner'] == owner
    assert event_args['value'] == 900


def test_withdraw_eth(testerchain, preallocation_escrow):
    owner = testerchain.client.accounts[1]
    log = preallocation_escrow.events.ETHWithdrawn.createFilter(fromBlock='latest')

    value = 1000
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': preallocation_escrow.address, 'value': value})
    testerchain.wait_for_receipt(tx)

    balance = testerchain.client.get_balance(owner)
    tx = preallocation_escrow.functions.withdrawETH().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert testerchain.client.get_balance(preallocation_escrow.address) == 0
    assert testerchain.client.get_balance(owner) == balance + value

    events = log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['owner'] == owner
    assert event_args['value'] == value

    # Can't withdraw again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = preallocation_escrow.functions.withdrawETH().transact({'from': owner})
        testerchain.wait_for_receipt(tx)


def test_receive_approval(testerchain, token, preallocation_escrow, escrow):
    creator = testerchain.client.accounts[0]
    deposits = preallocation_escrow.events.TokensDeposited.createFilter(fromBlock='latest')

    # Deposit some tokens to the preallocation escrow and lock them
    value = 2000
    duration = 1000
    tx = token.functions.approveAndCall(preallocation_escrow.address, value, testerchain.w3.toBytes(duration)).transact()
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(preallocation_escrow.address).call() == value
    assert preallocation_escrow.functions.getLockedTokens().call() == value

    events = deposits.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == creator
    assert event_args['value'] == value
    assert event_args['duration'] == duration


def test_reentrancy(testerchain, preallocation_escrow, deploy_contract):
    owner = testerchain.client.accounts[1]

    # Prepare contracts
    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    tx = preallocation_escrow.functions.transferOwnership(contract_address).transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Transfer ETH to the escrow
    value = 10000
    tx = reentrancy_contract.functions.setData(1, preallocation_escrow.address, value, bytes()).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': contract_address, 'value': value})
    testerchain.wait_for_receipt(tx)
    assert testerchain.client.get_balance(preallocation_escrow.address) == value

    # Try to withdraw ETH twice
    balance = testerchain.w3.eth.getBalance(contract_address)
    transaction = preallocation_escrow.functions.withdrawETH().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance
