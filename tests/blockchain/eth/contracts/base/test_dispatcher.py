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
from web3.exceptions import BadFunctionCallOutput

from nucypher.blockchain.eth.interfaces import Blockchain

SECRET_LENGTH = 16


@pytest.mark.slow
def test_dispatcher(testerchain):
    creator = testerchain.w3.eth.accounts[0]
    account = testerchain.w3.eth.accounts[1]

    secret = os.urandom(SECRET_LENGTH)
    secret_hash = testerchain.w3.keccak(secret)
    secret2 = os.urandom(SECRET_LENGTH)
    secret2_hash = testerchain.w3.keccak(secret2)
    secret3 = os.urandom(SECRET_LENGTH)
    secret3_hash = testerchain.w3.keccak(secret3)

    # Try to deploy broken libraries and dispatcher for them
    contract0_bad_lib, _ = testerchain.deploy_contract('BadDispatcherStorage')
    contract2_bad_verify_state_lib, _ = testerchain.deploy_contract('ContractV2BadVerifyState')
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('Dispatcher', contract0_bad_lib.address, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('Dispatcher', contract2_bad_verify_state_lib.address, secret_hash)

    # Deploy contracts and dispatcher for them
    contract1_lib, _ = testerchain.deploy_contract('ContractV1', 1)
    contract2_lib, _ = testerchain.deploy_contract('ContractV2', 1)
    contract3_lib, _ = testerchain.deploy_contract('ContractV3', 2)
    contract4_lib, _ = testerchain.deploy_contract('ContractV4', 3)
    contract2_bad_storage_lib, _ = testerchain.deploy_contract('ContractV2BadStorage')
    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract1_lib.address, secret_hash)
    assert contract1_lib.address == dispatcher.functions.target().call()

    upgrades = dispatcher.events.Upgraded.createFilter(fromBlock=0)
    state_verifications = dispatcher.events.StateVerified.createFilter(fromBlock=0)
    upgrade_finishings = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0)

    events = upgrades.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert Blockchain.NULL_ADDRESS == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    events = state_verifications.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract1_lib.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = upgrade_finishings.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract1_lib.address == event_args['target']
    assert creator == event_args['sender']

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = testerchain.w3.eth.contract(
        abi=contract1_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.verifyState(contract1_lib.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract1_lib.functions.finishUpgrade(contract1_lib.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract1_lib.functions.verifyState(contract1_lib.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Check values and methods before upgrade
    assert 1 == contract_instance.functions.storageValue().call()
    assert 10 == contract_instance.functions.returnValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 5 == contract_instance.functions.storageValue().call()
    tx = contract_instance.functions.pushArrayValue(12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 1 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    tx = contract_instance.functions.pushArrayValue(232).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    tx = contract_instance.functions.setMappingValue(14, 41).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 41 == contract_instance.functions.mappingValues(14).call()
    tx = contract_instance.functions.pushStructureValue1(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract_instance.functions.arrayStructures(0).call()
    tx = contract_instance.functions.pushStructureArrayValue1(0, 11).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = contract_instance.functions.pushStructureArrayValue1(0, 111).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    tx = contract_instance.functions.pushStructureValue2(4).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 4 == contract_instance.functions.mappingStructures(0).call()
    tx = contract_instance.functions.pushStructureArrayValue2(0, 12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    tx = contract_instance.functions.setDynamicallySizedValue('Hola').transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 'Hola' == contract_instance.functions.dynamicallySizedValue().call()

    # Only owner can change target address for the dispatcher
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract2_lib.address, secret, secret2_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Owner must know the secret
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract2_lib.address, secret2, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Owner can't use the same secret again because it's insecure
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract2_lib.address, secret, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_storage_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_verify_state_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Upgrade contract
    assert contract1_lib.address == dispatcher.functions.target().call()
    tx = dispatcher.functions.upgrade(contract2_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract2_lib.address == dispatcher.functions.target().call()

    events = upgrades.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert contract1_lib.address == event_args['from']
    assert contract2_lib.address == event_args['to']
    assert creator == event_args['owner']

    events = state_verifications.get_all_entries()
    assert 3 == len(events)
    event_args = events[1]['args']
    assert contract2_lib.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']

    events = upgrade_finishings.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert contract2_lib.address == event_args['target']
    assert creator == event_args['sender']

    # Check values and methods after upgrade
    assert 20 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.storageValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10 == contract_instance.functions.storageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    tx = contract_instance.functions.setMappingValue(13, 31).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 41 == contract_instance.functions.mappingValues(14).call()
    assert 31 == contract_instance.functions.mappingValues(13).call()
    tx = contract_instance.functions.pushStructureValue1(4).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract_instance.functions.arrayStructures(0).call()
    assert 4 == contract_instance.functions.arrayStructures(1).call()
    tx = contract_instance.functions.pushStructureArrayValue1(0, 12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    tx = contract_instance.functions.pushStructureValue2(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 4 == contract_instance.functions.mappingStructures(0).call()
    assert 5 == contract_instance.functions.mappingStructures(1).call()
    tx = contract_instance.functions.pushStructureArrayValue2(0, 13).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 'Hola' == contract_instance.functions.dynamicallySizedValue().call()
    tx = contract_instance.functions.setDynamicallySizedValue('Hello').transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 'Hello' == contract_instance.functions.dynamicallySizedValue().call()

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = testerchain.w3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Check new method and finishUpgrade method
    assert 1 == contract_instance.functions.storageValueToCheck().call()
    tx = contract_instance.functions.setStructureValueToCheck2(0, 55).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert [4, 55] == contract_instance.functions.mappingStructures(0).call()

    # Can't downgrade to the first version due to new storage variables
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract1_lib.address, secret2, secret3_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # And can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_storage_lib.address, secret2, secret3_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_verify_state_lib.address, secret2, secret3_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    assert contract2_lib.address == dispatcher.functions.target().call()

    rollbacks = dispatcher.events.RolledBack.createFilter(fromBlock='latest')

    # Only owner can rollback
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret2, secret3_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Owner must know the secret
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret3, secret3_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Owner can't use the same secret again because it's insecure
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret2, secret2_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Can rollback to the first version
    tx = dispatcher.functions.rollback(secret2, secret3_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract1_lib.address == dispatcher.functions.target().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    assert 1 == contract_instance.functions.storageValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 5 == contract_instance.functions.storageValue().call()

    events = rollbacks.get_all_entries()  # FIXME
    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract2_lib.address == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    events = state_verifications.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert contract2_lib.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = upgrade_finishings.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert contract1_lib.address == event_args['target']
    assert creator == event_args['sender']

    # Can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_storage_lib.address, secret3, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions\
            .upgrade(contract2_bad_verify_state_lib.address, secret3, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    assert contract1_lib.address == dispatcher.functions.target().call()

    # Create Event
    contract_instance = testerchain.w3.eth.contract(
        abi=contract1_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    test_events = contract_instance.events.EventV1.createFilter(fromBlock=0)
    tx = contract_instance.functions.createEvent(33).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    events = test_events.get_all_entries()
    assert 1 == len(events)
    assert 33 == events[0]['args']['value']

    # Upgrade to the version 3
    tx = dispatcher.functions.upgrade(contract2_lib.address, secret3, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = dispatcher.functions.upgrade(contract3_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    contract_instance = testerchain.w3.eth.contract(
        abi=contract3_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert contract3_lib.address == dispatcher.functions.target().call()
    assert 20 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.storageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    assert 41 == contract_instance.functions.mappingValues(14).call()
    assert 31 == contract_instance.functions.mappingValues(13).call()
    assert 3 == contract_instance.functions.arrayStructures(0).call()
    assert 4 == contract_instance.functions.arrayStructures(1).call()
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    assert [4, 55] == contract_instance.functions.mappingStructures(0).call()
    assert [5, 0] == contract_instance.functions.mappingStructures(1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 2 == contract_instance.functions.storageValueToCheck().call()
    assert 'Hello' == contract_instance.functions.dynamicallySizedValue().call()
    tx = contract_instance.functions.setAnotherStorageValue(77).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 77 == contract_instance.functions.anotherStorageValue().call()

    events = upgrades.get_all_entries()
    assert 4 == len(events)
    event_args = events[2]['args']
    assert contract1_lib.address == event_args['from']
    assert contract2_lib.address == event_args['to']
    assert creator == event_args['owner']
    event_args = events[3]['args']
    assert contract2_lib.address == event_args['from']
    assert contract3_lib.address == event_args['to']
    assert creator == event_args['owner']

    events = state_verifications.get_all_entries()
    assert 8 == len(events)
    event_args = events[4]['args']
    assert contract2_lib.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[5]['args']
    event_args = events[6]['args']
    assert contract3_lib.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[7]['args']

    events = upgrade_finishings.get_all_entries()
    assert 5 == len(events)
    event_args = events[3]['args']
    assert contract2_lib.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[4]['args']
    assert contract3_lib.address == event_args['target']
    assert creator == event_args['sender']

    # Create and check events
    tx = contract_instance.functions.createEvent(22).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    test_event_v2_log = contract_instance.events.EventV2.createFilter(fromBlock=0)
    events = test_event_v2_log.get_all_entries()
    assert 1 == len(events)
    assert 22 == events[0]['args']['value']

    contract_instance = testerchain.w3.eth.contract(
        abi=contract1_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    test_event_v1_log = contract_instance.events.EventV1.createFilter(fromBlock=0)
    events = test_event_v1_log.get_all_entries()
    assert 1 == len(events)
    assert 33 == events[0]['args']['value']

    # Check upgrading to the contract with explicit storage slots
    tx = dispatcher.functions.upgrade(contract4_lib.address, secret2, secret3_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    contract_instance = testerchain.w3.eth.contract(
        abi=contract4_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert contract4_lib.address == dispatcher.functions.target().call()
    assert 30 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.storageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    assert 41 == contract_instance.functions.mappingValues(14).call()
    assert 31 == contract_instance.functions.mappingValues(13).call()
    assert 3 == contract_instance.functions.arrayStructures(0).call()
    assert 4 == contract_instance.functions.arrayStructures(1).call()
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    assert [4, 55] == contract_instance.functions.mappingStructures(0).call()
    assert [5, 0] == contract_instance.functions.mappingStructures(1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 3 == contract_instance.functions.storageValueToCheck().call()
    assert 'Hello' == contract_instance.functions.dynamicallySizedValue().call()
    assert 77 == contract_instance.functions.anotherStorageValue().call()

    events = state_verifications.get_all_entries()
    assert 10 == len(events)
    event_args = events[8]['args']
    assert contract4_lib.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[9]['args']

    events = upgrade_finishings.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert contract4_lib.address == event_args['target']
    assert creator == event_args['sender']

    # Upgrade to the previous version - check that new `verifyState` can handle old contract
    tx = dispatcher.functions.upgrade(contract3_lib.address, secret3, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract3_lib.address == dispatcher.functions.target().call()
    assert 20 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.storageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.arrayValues(0).call()
    assert 232 == contract_instance.functions.arrayValues(1).call()
    assert 41 == contract_instance.functions.mappingValues(14).call()
    assert 31 == contract_instance.functions.mappingValues(13).call()
    assert 3 == contract_instance.functions.arrayStructures(0).call()
    assert 4 == contract_instance.functions.arrayStructures(1).call()
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    assert [4, 55] == contract_instance.functions.mappingStructures(0).call()
    assert [5, 0] == contract_instance.functions.mappingStructures(1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 2 == contract_instance.functions.storageValueToCheck().call()
    assert 'Hello' == contract_instance.functions.dynamicallySizedValue().call()
    assert 77 == contract_instance.functions.anotherStorageValue().call()

    events = state_verifications.get_all_entries()
    assert 12 == len(events)
    event_args = events[10]['args']
    assert contract3_lib.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[11]['args']


@pytest.mark.slow
def test_selfdestruct(testerchain):
    creator = testerchain.w3.eth.accounts[0]
    account = testerchain.w3.eth.accounts[1]

    secret = os.urandom(SECRET_LENGTH)
    secret_hash = testerchain.w3.keccak(secret)
    secret2 = os.urandom(SECRET_LENGTH)
    secret2_hash = testerchain.w3.keccak(secret2)
    secret3 = os.urandom(SECRET_LENGTH)
    secret3_hash = testerchain.w3.keccak(secret3)

    # Deploy contract and destroy it
    contract1_lib, _ = testerchain.deploy_contract('Destroyable', 22)
    assert 22 == contract1_lib.functions.constructorValue().call()
    tx = contract1_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((BadFunctionCallOutput, ValueError)):
        contract1_lib.functions.constructorValue().call()

    # Can't create dispatcher using address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('Dispatcher', Blockchain.NULL_ADDRESS, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('Dispatcher', account, secret_hash)
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.deploy_contract('Dispatcher', contract1_lib.address, secret_hash)

    # Deploy contract again with a dispatcher targeting it
    contract2_lib, _ = testerchain.deploy_contract('Destroyable', 23)
    dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract2_lib.address, secret_hash)
    assert contract2_lib.address == dispatcher.functions.target().call()

    contract_instance = testerchain.w3.eth.contract(
        abi=contract1_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    tx = contract_instance.functions.setFunctionValue(34).transact()
    testerchain.wait_for_receipt(tx)
    assert 23 == contract_instance.functions.constructorValue().call()
    assert 34 == contract_instance.functions.functionValue().call()

    # Can't upgrade to an address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(Blockchain.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract1_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Destroy library
    tx = contract2_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    # Dispatcher must determine that there is no contract
    with pytest.raises((TransactionFailed, ValueError)):
        contract_instance.functions.constructorValue().call()

    # Can't upgrade to an address without contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(Blockchain.NULL_ADDRESS, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(account, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract1_lib.address, secret, secret2_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Deploy the same contract again and upgrade to this contract
    contract3_lib, _ = testerchain.deploy_contract('Destroyable', 24)
    tx = dispatcher.functions.upgrade(contract3_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 24 == contract_instance.functions.constructorValue().call()
    assert 34 == contract_instance.functions.functionValue().call()

    # Can't rollback because the previous version is destroyed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret2, secret3_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Destroy again
    tx = contract3_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        contract_instance.functions.constructorValue().call()

    # Still can't rollback because the previous version is destroyed
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret2, secret3_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Deploy the same contract twice and upgrade to the latest contract
    contract4_lib, _ = testerchain.deploy_contract('Destroyable', 25)
    contract5_lib, _ = testerchain.deploy_contract('Destroyable', 26)
    tx = dispatcher.functions.upgrade(contract4_lib.address, secret2, secret3_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = dispatcher.functions.upgrade(contract5_lib.address, secret3, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 26 == contract_instance.functions.constructorValue().call()
    assert 34 == contract_instance.functions.functionValue().call()

    # Destroy the previous version of the contract and try to rollback again
    tx = contract4_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.rollback(secret, secret2_hash).transact({'from': account})
        testerchain.wait_for_receipt(tx)

    # Deploy the same contract again and upgrade
    contract6_lib, _ = testerchain.deploy_contract('Destroyable', 27)
    tx = dispatcher.functions.upgrade(contract6_lib.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 27 == contract_instance.functions.constructorValue().call()
    assert 34 == contract_instance.functions.functionValue().call()

    # Destroy the current version of the contract
    tx = contract6_lib.functions.destroy().transact()
    testerchain.wait_for_receipt(tx)
    # Now rollback must work, the previous version is fine
    tx = dispatcher.functions.rollback(secret2, secret3_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 26 == contract_instance.functions.constructorValue().call()
    assert 34 == contract_instance.functions.functionValue().call()
