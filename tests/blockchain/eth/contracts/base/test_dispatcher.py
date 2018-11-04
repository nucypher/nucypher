"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract

SECRET_LENGTH = 32


@pytest.mark.slow
def test_dispatcher(testerchain):
    creator = testerchain.interface.w3.eth.accounts[0]
    account = testerchain.interface.w3.eth.accounts[1]

    secret = os.urandom(SECRET_LENGTH)
    secret_hash = testerchain.interface.w3.sha3(secret)
    secret2 = os.urandom(SECRET_LENGTH)
    secret2_hash = testerchain.interface.w3.sha3(secret2)
    secret3 = os.urandom(SECRET_LENGTH)
    secret3_hash = testerchain.interface.w3.sha3(secret3)

    # Load contract interface
    contract_interface = testerchain.interface.get_contract_factory('ContractInterface')

    # Deploy contracts and dispatcher for them
    contract1_lib, _ = testerchain.interface.deploy_contract('ContractV1', 1)
    contract2_lib, _ = testerchain.interface.deploy_contract('ContractV2', 1)
    contract3_lib, _ = testerchain.interface.deploy_contract('ContractV3', 2)
    contract2_bad_lib, _ = testerchain.interface.deploy_contract('ContractV2Bad')
    dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract1_lib.address, secret_hash)

    upgrades = dispatcher.events.Upgraded.createFilter(fromBlock=0)
    assert contract1_lib.address == dispatcher.functions.target().call()

    events = upgrades.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert '0x' + '0' * 40 == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = testerchain.interface.w3.eth.contract(
        abi=contract_interface.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Check values and methods before upgrade
    assert 1 == contract_instance.functions.getStorageValue().call()
    assert 10 == contract_instance.functions.returnValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 5 == contract_instance.functions.getStorageValue().call()
    tx = contract_instance.functions.pushArrayValue(12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 1 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.getArrayValue(0).call()
    tx = contract_instance.functions.pushArrayValue(232).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 232 == contract_instance.functions.getArrayValue(1).call()
    tx = contract_instance.functions.setMappingValue(14, 41).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 41 == contract_instance.functions.getMappingValue(14).call()
    tx = contract_instance.functions.pushStructureValue1(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract_instance.functions.getStructureValue1(0).call()
    tx = contract_instance.functions.pushStructureArrayValue1(0, 11).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = contract_instance.functions.pushStructureArrayValue1(0, 111).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    tx = contract_instance.functions.pushStructureValue2(4).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 4 == contract_instance.functions.getStructureValue2(0).call()
    tx = contract_instance.functions.pushStructureArrayValue2(0, 12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    tx = contract_instance.functions.setDynamicallySizedValue('Hola').transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 'Hola' == contract_instance.functions.getDynamicallySizedValue().call()

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
        tx = dispatcher.functions.upgrade(contract2_bad_lib.address, secret, secret2_hash).transact({'from': creator})
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

    # Check values and methods after upgrade
    assert 20 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.getStorageValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10 == contract_instance.functions.getStorageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.getArrayValue(0).call()
    assert 232 == contract_instance.functions.getArrayValue(1).call()
    tx = contract_instance.functions.setMappingValue(13, 31).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 41 == contract_instance.functions.getMappingValue(14).call()
    assert 31 == contract_instance.functions.getMappingValue(13).call()
    tx = contract_instance.functions.pushStructureValue1(4).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract_instance.functions.getStructureValue1(0).call()
    assert 4 == contract_instance.functions.getStructureValue1(1).call()
    tx = contract_instance.functions.pushStructureArrayValue1(0, 12).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    tx = contract_instance.functions.pushStructureValue2(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 4 == contract_instance.functions.getStructureValue2(0).call()
    assert 5 == contract_instance.functions.getStructureValue2(1).call()
    tx = contract_instance.functions.pushStructureArrayValue2(0, 13).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 'Hola' == contract_instance.functions.getDynamicallySizedValue().call()
    tx = contract_instance.functions.setDynamicallySizedValue('Hello').transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 'Hello' == contract_instance.functions.getDynamicallySizedValue().call()

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = testerchain.interface.w3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Check new method and finishUpgrade method
    assert 1 == contract_instance.functions.storageValueToCheck().call()
    tx = contract_instance.functions.setStructureValueToCheck2(0, 55).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 55 == contract_instance.functions.getStructureValueToCheck2(0).call()

    # Can't downgrade to the first version due to new storage variables
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract1_lib.address, secret2, secret3_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # And can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract2_bad_lib.address, secret2, secret3_hash).transact({'from': creator})
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
    assert 12 == contract_instance.functions.getArrayValue(0).call()
    assert 232 == contract_instance.functions.getArrayValue(1).call()
    assert 1 == contract_instance.functions.getStorageValue().call()
    tx = contract_instance.functions.setStorageValue(5).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 5 == contract_instance.functions.getStorageValue().call()

    events = rollbacks.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract2_lib.address == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract2_bad_lib.address, secret3, secret_hash).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    assert contract1_lib.address == dispatcher.functions.target().call()

    # Create Event
    contract_instance = testerchain.interface.w3.eth.contract(
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
    contract_instance = testerchain.interface.w3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert contract3_lib.address == dispatcher.functions.target().call()
    assert 20 == contract_instance.functions.returnValue().call()
    assert 5 == contract_instance.functions.getStorageValue().call()
    assert 2 == contract_instance.functions.getArrayValueLength().call()
    assert 12 == contract_instance.functions.getArrayValue(0).call()
    assert 232 == contract_instance.functions.getArrayValue(1).call()
    assert 41 == contract_instance.functions.getMappingValue(14).call()
    assert 31 == contract_instance.functions.getMappingValue(13).call()
    assert 5 == contract_instance.functions.getStorageValue().call()
    assert 3 == contract_instance.functions.getStructureValue1(0).call()
    assert 4 == contract_instance.functions.getStructureValue1(1).call()
    assert 11 == contract_instance.functions.getStructureArrayValue1(0, 0).call()
    assert 111 == contract_instance.functions.getStructureArrayValue1(0, 1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue1(0, 2).call()
    assert 4 == contract_instance.functions.getStructureValue2(0).call()
    assert 5 == contract_instance.functions.getStructureValue2(1).call()
    assert 12 == contract_instance.functions.getStructureArrayValue2(0, 0).call()
    assert 13 == contract_instance.functions.getStructureArrayValue2(0, 1).call()
    assert 55 == contract_instance.functions.getStructureValueToCheck2(0).call()
    assert 2 == contract_instance.functions.storageValueToCheck().call()
    assert 'Hello' == contract_instance.functions.getDynamicallySizedValue().call()

    # bug? with duplicate entries
    upgrades = dispatcher.events.Upgraded.createFilter(fromBlock=0)
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

    # Create and check events
    tx = contract_instance.functions.createEvent(22).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    test_event_v2_log = contract_instance.events.EventV2.createFilter(fromBlock=0)
    events = test_event_v2_log.get_all_entries()
    assert 1 == len(events)
    assert 22 == events[0]['args']['value']

    contract_instance = testerchain.interface.w3.eth.contract(
        abi=contract1_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    test_event_v1_log = contract_instance.events.EventV1.createFilter(fromBlock=0)
    events = test_event_v1_log.get_all_entries()
    assert 1 == len(events)
    assert 33 == events[0]['args']['value']
