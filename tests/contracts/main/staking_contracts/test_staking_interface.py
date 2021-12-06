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

from nucypher.blockchain.eth.constants import NULL_ADDRESS


@pytest.fixture()
def staking_contract(testerchain, router, deploy_contract):
    creator = testerchain.client.accounts[0]
    user = testerchain.client.accounts[1]

    contract, _ = deploy_contract('SimpleStakingContract', router.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def staking_contract_interface(testerchain, staking_interface, staking_contract):
    return testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=staking_contract.address,
        ContractFactoryClass=Contract)


def test_nonexistent_method(testerchain, policy_manager, staking_contract):
    """
    Test that interface executes only predefined methods
    """
    owner = testerchain.client.accounts[1]

    # Create fake instance of the user escrow contract
    fake_preallocation_escrow = testerchain.client.get_contract(
        abi=policy_manager.abi,
        address=staking_contract.address,
        ContractFactoryClass=Contract)

    # Can't execute method that not in the interface
    with pytest.raises((TransactionFailed, ValueError)):
        tx = fake_preallocation_escrow.functions.additionalMethod(1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)


def test_staker(testerchain, token, escrow, staking_contract, staking_contract_interface, staking_interface):
    """
    Test staker functions in the staking interface
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    # Owner can't use the staking interface directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.withdrawAsStaker(100).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.setSnapshots(False).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # staker_withdraws = staking_contract_interface.events.WithdrawnAsStaker.createFilter(fromBlock='latest')
    snapshots_logs = staking_contract_interface.events.SnapshotSet.createFilter(fromBlock='latest')

    # Use stakers methods through the staking contract
    value = 1600
    escrow_balance = token.functions.balanceOf(escrow.address).call()
    tx = token.functions.transfer(staking_contract.address, 10 * value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.depositAsStaker(2 * value).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.withdrawAsStaker(value).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.value().call() == value
    assert token.functions.balanceOf(escrow.address).call() == escrow_balance + value
    assert token.functions.balanceOf(staking_contract.address).call() == 9 * value

    # Test snapshots
    tx = staking_contract_interface.functions.setSnapshots(True).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.snapshots().call()

    events = snapshots_logs.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert event_args['snapshotsEnabled']


def test_policy(testerchain, policy_manager, staking_contract, staking_contract_interface):
    """
    Test policy manager functions in the staking interface
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    owner_balance = testerchain.client.get_balance(owner)

    # Nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.withdrawPolicyFee().transact({'from': owner, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    assert owner_balance == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(staking_contract.address)

    # Send ETH to the policy manager as a fee for the owner
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': policy_manager.address, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    staker_fee = staking_contract_interface.events.PolicyFeeWithdrawn.createFilter(fromBlock='latest')

    # Only owner can withdraw fee
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.withdrawPolicyFee().transact({'from': creator, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Owner withdraws fee
    tx = staking_contract_interface.functions.withdrawPolicyFee().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert 10000 == testerchain.client.get_balance(staking_contract.address)
    assert owner_balance == testerchain.client.get_balance(owner)
    assert 0 == testerchain.client.get_balance(policy_manager.address)
    assert 10000 == testerchain.client.get_balance(staking_contract.address)

    events = staker_fee.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 10000 == event_args['value']

    # Only owner can set min fee rate
    min_fee_sets = staking_contract_interface.events.MinFeeRateSet.createFilter(fromBlock='latest')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.setMinFeeRate(333).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.setMinFeeRate(222).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert 222 == policy_manager.functions.minFeeRate().call()

    events = min_fee_sets.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert owner == event_args['sender']
    assert 222 == event_args['value']


def test_worklock(testerchain, worklock, staking_contract, staking_contract_interface, staking_interface):
    """
    Test worklock functions in the staking interface
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    bids = staking_contract_interface.events.Bid.createFilter(fromBlock='latest')
    claims = staking_contract_interface.events.Claimed.createFilter(fromBlock='latest')
    refunds = staking_contract_interface.events.Refund.createFilter(fromBlock='latest')
    cancellations = staking_contract_interface.events.BidCanceled.createFilter(fromBlock='latest')
    compensations = staking_contract_interface.events.CompensationWithdrawn.createFilter(fromBlock='latest')

    # Owner can't use the staking interface directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.bid(0).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.cancelBid().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.withdrawCompensation().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.claim().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.refund().transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Send ETH to to the escrow
    bid = 10000
    tx = testerchain.client.send_transaction(
        {'from': testerchain.client.coinbase, 'to': staking_contract.address, 'value': 2 * bid})
    testerchain.wait_for_receipt(tx)

    # Bid
    assert worklock.functions.depositedETH().call() == 0
    assert testerchain.client.get_balance(staking_contract.address) == 2 * bid
    tx = staking_contract_interface.functions.bid(bid).transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.depositedETH().call() == bid
    assert testerchain.client.get_balance(staking_contract.address) == bid

    events = bids.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['depositedETH'] == bid

    # Cancel bid
    tx = staking_contract_interface.functions.cancelBid().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.depositedETH().call() == 0
    assert testerchain.client.get_balance(staking_contract.address) == 2 * bid

    events = cancellations.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner

    # Withdraw compensation
    compensation = 11000
    tx = worklock.functions.sendCompensation().transact({'from': creator, 'value': compensation, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.compensationValue().call() == compensation
    tx = staking_contract_interface.functions.withdrawCompensation().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.compensationValue().call() == 0
    assert testerchain.client.get_balance(staking_contract.address) == 2 * bid + compensation

    events = compensations.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner

    # Claim
    assert worklock.functions.claimed().call() == 0
    tx = staking_contract_interface.functions.claim().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.claimed().call() == 1

    events = claims.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['claimedTokens'] == 1

    # Withdraw refund
    refund = 12000
    tx = worklock.functions.sendRefund().transact({'from': creator, 'value': refund, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.refundETH().call() == refund
    tx = staking_contract_interface.functions.refund().transact({'from': owner, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.refundETH().call() == 0
    assert testerchain.client.get_balance(staking_contract.address) == 2 * bid + compensation + refund

    events = refunds.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['refundETH'] == refund


def test_interface_without_worklock(testerchain,
                                    deploy_contract,
                                    token,
                                    escrow,
                                    policy_manager,
                                    worklock,
                                    threshold_staking):
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]

    staking_interface, _ = deploy_contract(
        'StakingInterface',
        token.address,
        escrow.address,
        policy_manager.address,
        worklock.address,
        threshold_staking.address
    )
    router, _ = deploy_contract('StakingInterfaceRouter', staking_interface.address)

    staking_contract, _ = deploy_contract('SimpleStakingContract', router.address)
    # Transfer ownership
    tx = staking_contract.functions.transferOwnership(owner).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    staking_contract_interface = testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=staking_contract.address,
        ContractFactoryClass=Contract)

    # All worklock methods work
    tx = staking_contract_interface.functions.bid(0).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.cancelBid().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.withdrawCompensation().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.claim().transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    tx = staking_contract_interface.functions.refund().transact({'from': owner})
    testerchain.wait_for_receipt(tx)

    # Test interface without worklock
    staking_interface, _ = deploy_contract(
        'StakingInterface',
        token.address,
        escrow.address,
        policy_manager.address,
        NULL_ADDRESS,
        threshold_staking.address
    )
    tx = router.functions.upgrade(staking_interface.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Current version of interface doesn't have worklock contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.bid(0).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.cancelBid().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.withdrawCompensation().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.claim().transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_contract_interface.functions.refund().transact({'from': owner})
        testerchain.wait_for_receipt(tx)


def test_threshold_staking(testerchain,
                           threshold_staking,
                           staking_contract,
                           staking_contract_interface,
                           staking_interface):
    """
    Test Threshold staking functions in the staking interface
    """
    creator = testerchain.client.accounts[0]
    owner = testerchain.client.accounts[1]
    operator = testerchain.client.accounts[2]
    beneficiary = testerchain.client.accounts[3]
    authorizer = testerchain.client.accounts[4]

    stakes = staking_contract_interface.events.ThresholdNUStaked.createFilter(fromBlock='latest')
    unstakes = staking_contract_interface.events.ThresholdNUUnstaked.createFilter(fromBlock='latest')

    # Owner can't use the staking interface directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.stakeNu(operator, beneficiary, authorizer).transact({'from': owner})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = staking_interface.functions.unstakeNu(operator, 1).transact({'from': owner})
        testerchain.wait_for_receipt(tx)

    # Stake NU
    assert threshold_staking.functions.stakedNuInT().call() == 0
    tx = staking_contract_interface.functions.stakeNu(operator, beneficiary, authorizer).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert threshold_staking.functions.operator().call() == operator
    assert threshold_staking.functions.beneficiary().call() == beneficiary
    assert threshold_staking.functions.authorizer().call() == authorizer
    assert threshold_staking.functions.stakedNuInT().call() != 0

    events = stakes.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == owner
    assert event_args['operator'] == operator
    assert event_args['beneficiary'] == beneficiary
    assert event_args['authorizer'] == authorizer

    # Unstake NU
    staked = threshold_staking.functions.stakedNuInT().call()
    unstaked = staked // 3
    tx = staking_contract_interface.functions.unstakeNu(operator, unstaked).transact({'from': owner})
    testerchain.wait_for_receipt(tx)
    assert threshold_staking.functions.stakedNuInT().call() == staked - unstaked

    events = unstakes.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert event_args['sender'] == owner
    assert event_args['operator'] == operator
    assert event_args['amount'] == unstaked
