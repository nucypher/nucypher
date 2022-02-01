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

from bisect import bisect

import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3
from web3.contract import Contract

from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import NU
from nucypher.utilities.ethereum import get_array_data_location, get_mapping_entry_location, to_bytes32


def test_upgrading(testerchain, token, deploy_contract):
    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]
    worker = testerchain.client.accounts[2]

    # Initialize contract and staker
    worklock, _ = deploy_contract('WorkLockForStakingEscrowMock', token.address)
    threshold_staking, _ = deploy_contract('ThresholdStakingForStakingEscrowMock')

    # Deploy contract
    contract_library_v1, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        worklock.address,
        threshold_staking.address
    )
    dispatcher, _ = deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = deploy_contract(
        contract_name='StakingEscrowV2Mock',
        _token=token.address,
        _workLock=worklock.address,
        _tStaking=threshold_staking.address
    )

    contract = testerchain.client.get_contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    tx = worklock.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    value = NU(100_000, 'NU').to_units()
    tx = token.functions.transfer(worklock.address, value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker, value, 0).transact({'from': staker})
    testerchain.wait_for_receipt(tx)

    # Upgrade to the second version
    tx = dispatcher.functions.upgrade(contract_library_v2.address).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check constructor and storage values
    assert dispatcher.functions.target().call() == contract_library_v2.address
    assert contract.functions.workLock().call() == worklock.address
    assert contract.functions.valueToCheck().call() == 2
    # Check new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract.functions.valueToCheck().call() == 3

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = deploy_contract(
        contract_name='StakingEscrowBad',
        _token=token.address,
        _workLock=worklock.address,
        _tStaking=threshold_staking.address
    )
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract_library_v1.address
    assert contract.functions.workLock().call() == worklock.address
    # After rollback new ABI is unavailable
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert len(events) == 4
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert event_args['sender'] == creator
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert event_args['sender'] == creator
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert event_args['sender'] == creator

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert len(events) == 3
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert event_args['sender'] == creator
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert event_args['sender'] == creator
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert event_args['sender'] == creator


def test_measure_work(testerchain, token, worklock, escrow, application_economics):
    creator, staker, *everyone_else = testerchain.w3.eth.accounts

    # Measured work must be 0 and completed work must be maximum even before deposit
    assert worklock.functions.setWorkMeasurement(staker, True).call() == 0
    assert worklock.functions.setWorkMeasurement(staker, False).call() == 0
    assert escrow.functions.getCompletedWork(staker).call() == application_economics.total_supply

    # Same behaviour after depositing tokens
    value = NU(15_000, 'NU').to_units()
    tx = token.functions.transfer(worklock.address, value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.setWorkMeasurement(staker, True).call() == 0
    assert worklock.functions.setWorkMeasurement(staker, False).call() == 0
    assert escrow.functions.getCompletedWork(staker).call() == application_economics.total_supply


def test_snapshots(testerchain, token, escrow, worklock, threshold_staking, application_economics):

    creator = testerchain.client.accounts[0]
    staker1 = testerchain.client.accounts[1]
    staker2 = testerchain.client.accounts[2]

    now = testerchain.get_block_number()
    assert escrow.functions.totalStakedForAt(staker1, now).call() == 0
    assert escrow.functions.totalStakedAt(now).call() == application_economics.total_supply

    # Staker deposits some tokens
    value = NU(15_000, 'NU').to_units()
    tx = token.functions.transfer(worklock.address, value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    initial_deposit = value // 100
    tx = worklock.functions.depositFromWorkLock(staker1, initial_deposit, 0).transact()
    testerchain.wait_for_receipt(tx)

    now = testerchain.get_block_number()
    assert escrow.functions.totalStakedForAt(staker1, now).call() == 0
    assert escrow.functions.totalStakedAt(now).call() == application_economics.total_supply

    # A SECOND STAKER APPEARS:

    # Staker 2 deposits some tokens. Since snapshots are disabled, no changes in history
    deposit_staker2 = 2 * initial_deposit
    tx = worklock.functions.depositFromWorkLock(staker2, deposit_staker2, 0).transact()
    testerchain.wait_for_receipt(tx)

    assert deposit_staker2 == escrow.functions.getAllTokens(staker2).call()
    now = testerchain.get_block_number()
    assert escrow.functions.totalStakedForAt(staker2, now).call() == 0
    assert escrow.functions.totalStakedAt(now).call() == application_economics.total_supply

    # Finally, the first staker withdraws some tokens
    withdrawal = 42
    tx = escrow.functions.withdraw(withdrawal).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    last_balance_staker1 = initial_deposit - withdrawal
    assert last_balance_staker1 == escrow.functions.getAllTokens(staker1).call()
    now = testerchain.get_block_number()
    assert escrow.functions.totalStakedForAt(staker1, now).call() == 0
    assert escrow.functions.totalStakedAt(now).call() == application_economics.total_supply
