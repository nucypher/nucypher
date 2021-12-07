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


def test_upgrading(testerchain, token, token_economics, deploy_contract):
    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]
    worker = testerchain.client.accounts[2]

    # Initialize contract and staker
    worklock, _ = deploy_contract('WorkLockForStakingEscrowMock', token.address)

    # Deploy contract
    contract_library_v1, _ = deploy_contract(
        'StakingEscrow',
        token.address,
        worklock.address
    )
    dispatcher, _ = deploy_contract('Dispatcher', contract_library_v1.address)

    # Deploy second version of the contract
    contract_library_v2, _ = deploy_contract(
        contract_name='StakingEscrowV2Mock',
        _token=token.address,
        _workLock=worklock.address
    )

    contract = testerchain.client.get_contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    tx = worklock.functions.setStakingEscrow(contract.address).transact()
    testerchain.wait_for_receipt(tx)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    value = NU(100_000, 'NU').to_nunits()
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
        _workLock=worklock.address
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


def test_flags(testerchain, token, escrow):
    staker = testerchain.client.accounts[1]

    snapshots_log = escrow.events.SnapshotSet.createFilter(fromBlock='latest')

    # Check flag defaults
    snapshots = escrow.functions.getFlags(staker).call()
    assert snapshots

    # There should be no events so far
    assert 0 == len(snapshots_log.get_all_entries())

    # Setting the flags to their current values should not affect anything, not even events
    tx = escrow.functions.setSnapshots(True).transact({'from': staker})
    testerchain.wait_for_receipt(tx)

    snapshots = escrow.functions.getFlags(staker).call()
    assert snapshots

    # There should be no events so far
    assert len(snapshots_log.get_all_entries()) == 0

    # Let's change the value of the snapshots flag: obviously, only this flag should be affected
    tx = escrow.functions.setSnapshots(False).transact({'from': staker})
    testerchain.wait_for_receipt(tx)

    snapshots = escrow.functions.getFlags(staker).call()
    assert not snapshots

    assert len(snapshots_log.get_all_entries()) == 1

    event_args = snapshots_log.get_all_entries()[-1]['args']
    assert staker == event_args['staker'] == staker
    assert not event_args['snapshotsEnabled']


def test_measure_work(testerchain, token, worklock, escrow, token_economics):
    creator, staker, *everyone_else = testerchain.w3.eth.accounts

    # Measured work must be 0 and completed work must be maximum even before deposit
    assert worklock.functions.setWorkMeasurement(staker, True).call() == 0
    assert worklock.functions.setWorkMeasurement(staker, False).call() == 0
    assert escrow.functions.getCompletedWork(staker).call() == token_economics.total_supply

    # Same behaviour after depositing tokens
    value = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.setWorkMeasurement(staker, True).call() == 0
    assert worklock.functions.setWorkMeasurement(staker, False).call() == 0
    assert escrow.functions.getCompletedWork(staker).call() == token_economics.total_supply


def test_snapshots(testerchain, token, escrow, worklock):

    # HELPER FUNCTIONS #

    class TestSnapshot:
        """Mimics how our Snapshots library work in a contract"""
        def __init__(self):
            self.history = {0: 0}
            self.timestamps = [0]

        def add_value_at(self, time, value):
            if self.timestamps[-1] == time:
                self.history[time] = value
                return
            elif time < self.timestamps[-1]:
                assert False
            self.timestamps.append(time)
            self.history[time] = value

        def add_value(self, value):
            self.add_value_at(testerchain.get_block_number(), value)

        def last_value(self):
            return self.history[self.timestamps[-1]]

        def get_value_at(self, time):
            if time > self.timestamps[-1]:
                return self.last_value()
            else:
                return self.history[self.timestamps[bisect(self.timestamps, time) - 1]]

        @classmethod
        def from_list(cls, snapshots):
            s = cls()
            for t, v in snapshots:
                s.timestamps.append(t)
                s.history[t] = v
            return s

        def __str__(self):
            return str(self.history)

        def __eq__(self, other):
            return self.history == other.history and self.timestamps == other.timestamps

    def staker_has_snapshots_enabled(staker) -> bool:
        snapshots_enabled = escrow.functions.getFlags(staker).call()
        return snapshots_enabled

    def decode_snapshots_from_slot(slot):
        slot = to_bytes32(slot)
        snapshot_2 = Web3.toInt(slot[:4]), Web3.toInt(slot[4:16])
        snapshot_1 = Web3.toInt(slot[16:20]), Web3.toInt(slot[20:32])
        return snapshot_1, snapshot_2

    def get_staker_history_from_storage(staker):
        STAKERS_MAPPING_SLOT = 6
        HISTORY_SLOT_IN_STAKER_INFO = 12

        # See https://solidity.readthedocs.io/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays
        staker_location = get_mapping_entry_location(key=to_bytes32(hexstr=staker),
                                                     mapping_location=STAKERS_MAPPING_SLOT)
        length_position = staker_location + HISTORY_SLOT_IN_STAKER_INFO

        data_position = get_array_data_location(length_position)

        length = testerchain.read_storage_slot(escrow.address, length_position)
        length_in_slots = (length + 1)//2
        slots = [testerchain.read_storage_slot(escrow.address, data_position + i) for i in range(length_in_slots)]
        snapshots = list()
        for snapshot_1, snapshot_2 in map(decode_snapshots_from_slot, slots):
            snapshots.append(snapshot_1)
            if snapshot_2 != (0, 0):
                snapshots.append(snapshot_2)
        return TestSnapshot.from_list(snapshots)

    def get_global_history_from_storage():
        GLOBAL_HISTORY_SLOT_IN_CONTRACT = 10
        # See https://solidity.readthedocs.io/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays
        length = testerchain.read_storage_slot(escrow.address, GLOBAL_HISTORY_SLOT_IN_CONTRACT)

        snapshots = list()
        for i in range(length):
            snapshot_bytes = Web3.toBytes(escrow.functions.balanceHistory(i).call()).rjust(16, b'\0')
            snapshots.append((Web3.toInt(snapshot_bytes[:4]), Web3.toInt(snapshot_bytes[4:16])))
        return TestSnapshot.from_list(snapshots)

    #
    # TEST STARTS HERE #
    #

    creator = testerchain.client.accounts[0]
    staker1 = testerchain.client.accounts[1]
    staker2 = testerchain.client.accounts[2]

    snapshot_log = escrow.events.SnapshotSet.createFilter(fromBlock='latest')

    expected_staker1_balance = TestSnapshot()
    expected_staker2_balance = TestSnapshot()
    expected_global_balance = TestSnapshot()
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_staker2_balance == get_staker_history_from_storage(staker2)
    assert expected_global_balance == get_global_history_from_storage()

    # Set snapshot parameter even before depositing. Disabling snapshots always creates a new snapshot with value 0
    assert staker_has_snapshots_enabled(staker1)
    tx = escrow.functions.setSnapshots(False).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert not staker_has_snapshots_enabled(staker1)
    expected_staker1_balance.add_value(0)
    expected_global_balance.add_value(0)
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_global_balance == get_global_history_from_storage()

    # Activating the snapshots again will create a new snapshot with current balance, which is 0
    tx = escrow.functions.setSnapshots(True).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert staker_has_snapshots_enabled(staker1)
    expected_staker1_balance.add_value(0)
    expected_global_balance.add_value(0)
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_global_balance == get_global_history_from_storage()

    # Check emitted events
    events = snapshot_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert not event_args['snapshotsEnabled']
    event_args = events[1]['args']
    assert staker1 == event_args['staker']
    assert event_args['snapshotsEnabled']

    # Staker deposits some tokens
    value = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    initial_deposit = value // 100
    tx = worklock.functions.depositFromWorkLock(staker1, initial_deposit, 0).transact()
    testerchain.wait_for_receipt(tx)

    expected_staker1_balance.add_value(initial_deposit)
    expected_global_balance.add_value(initial_deposit)
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_global_balance == get_global_history_from_storage()

    now = testerchain.get_block_number()
    assert escrow.functions.totalStakedForAt(staker1, now).call() == expected_staker1_balance.get_value_at(now)
    assert escrow.functions.totalStakedAt(now).call() == expected_global_balance.get_value_at(now)

    # Now that we do have a positive balance, let's deactivate snapshots and check them
    tx = escrow.functions.setSnapshots(False).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert not staker_has_snapshots_enabled(staker1)
    expected_staker1_balance.add_value(0)
    expected_global_balance.add_value(0)
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_global_balance == get_global_history_from_storage()

    assert initial_deposit == escrow.functions.getAllTokens(staker1).call()
    now = testerchain.get_block_number()
    assert 0 == escrow.functions.totalStakedForAt(staker1, now).call()
    assert 0 == escrow.functions.totalStakedAt(now).call()
    assert initial_deposit == escrow.functions.totalStakedForAt(staker1, now - 1).call()
    assert initial_deposit == escrow.functions.totalStakedAt(now - 1).call()

    # Activating the snapshots again will create a new snapshot with current balance (100)
    tx = escrow.functions.setSnapshots(True).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert staker_has_snapshots_enabled(staker1)
    expected_staker1_balance.add_value(initial_deposit)
    expected_global_balance.add_value(initial_deposit)
    assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    assert expected_global_balance == get_global_history_from_storage()

    now = testerchain.get_block_number()
    assert initial_deposit == escrow.functions.totalStakedForAt(staker1, now).call()
    assert initial_deposit == escrow.functions.totalStakedAt(now).call()
    assert 0 == escrow.functions.totalStakedForAt(staker1, now - 1).call()
    assert 0 == escrow.functions.totalStakedAt(now - 1).call()

    # A SECOND STAKER APPEARS:

    # Disable snapshots even before deposit. This creates a new snapshot with value 0
    balance_staker1 = escrow.functions.getAllTokens(staker1).call()
    assert staker_has_snapshots_enabled(staker2)
    tx = escrow.functions.setSnapshots(False).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert not staker_has_snapshots_enabled(staker2)
    expected_staker2_balance.add_value(0)
    expected_global_balance.add_value(balance_staker1)
    assert expected_staker2_balance == get_staker_history_from_storage(staker2)
    assert expected_global_balance == get_global_history_from_storage()

    # Staker 2 deposits some tokens. Since snapshots are disabled, no changes in history
    deposit_staker2 = 2 * initial_deposit
    tx = worklock.functions.depositFromWorkLock(staker2, deposit_staker2, 0).transact()
    testerchain.wait_for_receipt(tx)

    assert deposit_staker2 == escrow.functions.getAllTokens(staker2).call()
    assert expected_staker2_balance == get_staker_history_from_storage(staker2)
    assert expected_global_balance == get_global_history_from_storage()

    # Now that we do have a positive balance, let's activate snapshots and check them
    tx = escrow.functions.setSnapshots(True).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert staker_has_snapshots_enabled(staker2)
    expected_staker2_balance.add_value(deposit_staker2)
    expected_global_balance.add_value(balance_staker1 + deposit_staker2)
    assert expected_staker2_balance == get_staker_history_from_storage(staker2)
    assert expected_global_balance == get_global_history_from_storage()

    now = testerchain.get_block_number()
    assert deposit_staker2 == escrow.functions.totalStakedForAt(staker2, now).call()
    assert deposit_staker2 + balance_staker1 == escrow.functions.totalStakedAt(now).call()
    assert 0 == escrow.functions.totalStakedForAt(staker2, now - 1).call()
    assert balance_staker1 == escrow.functions.totalStakedAt(now - 1).call()

    # # Finally, the first staker withdraws some tokens
    # withdrawal = 42
    # tx = escrow.functions.withdraw(withdrawal).transact({'from': staker1})
    # testerchain.wait_for_receipt(tx)
    # last_balance_staker1 = balance_staker1 - withdrawal
    # assert last_balance_staker1 == escrow.functions.getAllTokens(staker1).call()
    #
    # expected_staker1_balance.add_value(last_balance_staker1)
    # expected_global_balance.add_value(last_balance_staker1 + deposit_staker2)
    # assert expected_staker1_balance == get_staker_history_from_storage(staker1)
    # assert expected_global_balance == get_global_history_from_storage()
    #
    # now = testerchain.get_block_number()
    # assert last_balance_staker1 == escrow.functions.totalStakedForAt(staker1, now).call()
    # assert last_balance_staker1 + deposit_staker2 == escrow.functions.totalStakedAt(now).call()
    # assert balance_staker1 == escrow.functions.totalStakedForAt(staker1, now - 1).call()
    # assert balance_staker1 + deposit_staker2 == escrow.functions.totalStakedAt(now - 1).call()
