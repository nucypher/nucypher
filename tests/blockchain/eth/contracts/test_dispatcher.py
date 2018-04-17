import pytest
from eth_tester.exceptions import TransactionFailed
from web3.contract import Contract


def test_dispatcher(web3, chain):
    """
    These are tests for Dispatcher taken from github:
    https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/test/UpgradableContractProxyTest.js
    but some of the tests are converted from javascript to python
    """

    creator = web3.eth.accounts[0]
    account = web3.eth.accounts[1]

    # Load contract interface
    contract_interface = chain.provider.get_contract_factory('ContractInterface')

    # Deploy contracts and dispatcher for them
    contract1_lib, _ = chain.provider.get_or_deploy_contract('ContractV1', 1)
    contract2_lib, _ = chain.provider.get_or_deploy_contract('ContractV2', 1)
    contract3_lib, _ = chain.provider.get_or_deploy_contract('ContractV3', 2)
    contract2_bad_lib, _ = chain.provider.get_or_deploy_contract('ContractV2Bad')
    dispatcher, _ = chain.provider.get_or_deploy_contract('Dispatcher', contract1_lib.address)

    upgrades = dispatcher.eventFilter('Upgraded')
    assert dispatcher.call().target() == contract1_lib.address

    # events = upgrades.get_all_entries()
    # assert 1 == len(events)

    # event_args = events[0]['args']
    # assert '0x' + '0' * 40 == event_args['from']
    # assert contract1_lib.address == event_args['to']
    # assert creator == event_args['owner']

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = web3.eth.contract(
        abi=contract_interface.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Only owner can change target address for dispatcher
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': account}).upgrade(contract2_lib.address)
        chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract1_lib.address

    # Check values before upgrade
    assert contract_instance.call().getStorageValue() == 1
    assert contract_instance.call().returnValue() == 10
    tx = contract_instance.transact().setStorageValue(5)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 5
    tx = contract_instance.transact().pushArrayValue(12)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getArrayValueLength() == 1
    assert contract_instance.call().getArrayValue(0) == 12
    tx = contract_instance.transact().pushArrayValue(232)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getArrayValueLength() == 2
    assert contract_instance.call().getArrayValue(1) == 232
    tx = contract_instance.transact().setMappingValue(14, 41)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getMappingValue(14) == 41
    tx = contract_instance.transact().pushStructureValue1(3)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureValue1(0) == 3
    tx = contract_instance.transact().pushStructureArrayValue1(0, 11)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureArrayValue1(0, 0) == 11
    tx = contract_instance.transact().pushStructureValue2(4)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureValue2(0) == 4
    tx = contract_instance.transact().pushStructureArrayValue2(0, 12)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureArrayValue2(0, 0) == 12

    # Can't upgrade to bad version
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract2_bad_lib.address)
        chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract1_lib.address

    # Upgrade contract
    tx = dispatcher.transact({'from': creator}).upgrade(contract2_lib.address)
    chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract2_lib.address

    # events = upgrades.get_all_entries()
    # assert 2 == len(events)
    #
    # event_args = events[1]['args']
    # assert contract1_lib.address == event_args['from']
    # assert contract2_lib.address == event_args['to']
    # assert creator == event_args['owner']

    # Check values after upgrade
    assert contract_instance.call().returnValue() == 20
    assert contract_instance.call().getStorageValue() == 5
    tx = contract_instance.transact().setStorageValue(5)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 10
    assert contract_instance.call().getArrayValueLength() == 2
    assert contract_instance.call().getArrayValue(0) == 12
    assert contract_instance.call().getArrayValue(1) == 232
    tx = contract_instance.transact().setMappingValue(13, 31)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getMappingValue(14) == 41
    assert contract_instance.call().getMappingValue(13) == 31
    tx = contract_instance.transact().pushStructureValue1(4)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureValue1(0) == 3
    assert contract_instance.call().getStructureValue1(1) == 4
    tx = contract_instance.transact().pushStructureArrayValue1(0, 12)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureArrayValue1(0, 0) == 11
    assert contract_instance.call().getStructureArrayValue1(0, 1) == 12
    tx = contract_instance.transact().pushStructureValue2(5)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureValue2(0) == 4
    assert contract_instance.call().getStructureValue2(1) == 5
    tx = contract_instance.transact().pushStructureArrayValue2(0, 13)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureArrayValue2(0, 0) == 12
    assert contract_instance.call().getStructureArrayValue2(0, 1) == 13

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = web3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Check new method and finish upgrade method
    assert contract_instance.call().storageValueToCheck() == 1
    tx = contract_instance.transact().setStructureValueToCheck2(0, 55)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStructureValueToCheck2(0) == 55

    # Can't downgrade to first version due to storage
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract1_lib.address)
        chain.wait_for_receipt(tx)

    # And can't upgrade to bad version
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract2_bad_lib.address)
        chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract2_lib.address

    rollbacks = dispatcher.eventFilter('RolledBack')

    # But can rollback
    tx = dispatcher.transact({'from': creator}).rollback()
    chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract1_lib.address
    assert contract_instance.call().getArrayValueLength() == 2
    assert contract_instance.call().getArrayValue(0) == 12
    assert contract_instance.call().getArrayValue(1) == 232
    assert contract_instance.call().getStorageValue() == 1
    tx = contract_instance.transact().setStorageValue(5)
    chain.wait_for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 5

    events = rollbacks.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract2_lib.address == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Can't upgrade to the bad version
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': creator}).upgrade(contract2_bad_lib.address)
        chain.wait_for_receipt(tx)
    assert dispatcher.call().target() == contract1_lib.address

    # Check dynamically sized value
    # TODO uncomment after fixing dispatcher
    # tx = contract_instance.transact().setDynamicallySizedValue('Hola')
    # chain.wait_for_receipt(tx)
    # assert contract_instance.call().getDynamicallySizedValue() == 'Hola'

    # # Create Event
    # contract_instance = web3.eth.contract(
    #     abi=contract1_lib.abi,
    #     address=dispatcher.address,
    #     ContractFactoryClass=Contract)
    # test_events = contract_instance.eventFilter('EventV1')
    # events = test_events.get_all_entries()
    # tx = contract_instance.transact().createEvent(33)
    # chain.wait_for_receipt(tx)
    # assert 1 == len(events)
    # assert 33 == events[0]['args']['value']

    # Upgrade to version 3
    tx = dispatcher.transact({'from': creator}).upgrade(contract2_lib.address)
    chain.wait_for_receipt(tx)
    tx = dispatcher.transact({'from': creator}).upgrade(contract3_lib.address)
    chain.wait_for_receipt(tx)
    contract_instance = web3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert dispatcher.call().target() == contract3_lib.address
    assert contract_instance.call().returnValue() == 20
    assert contract_instance.call().getStorageValue() == 5
    assert contract_instance.call().getArrayValueLength() == 2
    assert contract_instance.call().getArrayValue(0) == 12
    assert contract_instance.call().getArrayValue(1) == 232
    assert contract_instance.call().getMappingValue(14) == 41
    assert contract_instance.call().getMappingValue(13) == 31
    assert contract_instance.call().getStorageValue() == 5
    assert contract_instance.call().getStructureValue1(0) == 3
    assert contract_instance.call().getStructureValue1(1) == 4
    assert contract_instance.call().getStructureArrayValue1(0, 0) == 11
    assert contract_instance.call().getStructureArrayValue1(0, 1) == 12
    assert contract_instance.call().getStructureValue2(0) == 4
    assert contract_instance.call().getStructureValue2(1) == 5
    assert contract_instance.call().getStructureArrayValue2(0, 0) == 12
    assert contract_instance.call().getStructureArrayValue2(0, 1) == 13
    assert contract_instance.call().getStructureValueToCheck2(0) == 55
    assert contract_instance.call().storageValueToCheck() == 2

    # events = upgrades.get_all_entries()
    #
    # assert 4 == len(events)
    # event_args = events[2]['args']
    # assert contract1_lib.address == event_args['from']
    # assert contract2_lib.address == event_args['to']
    # assert creator == event_args['owner']
    # event_args = events[3]['args']
    # assert contract2_lib.address == event_args['from']
    # assert contract3_lib.address == event_args['to']
    # assert creator == event_args['owner']
    #
    # # Create and check events
    # tx = contract_instance.transact().createEvent(22)
    # chain.wait_for_receipt(tx)
    # events = contract_instance.pastEvents('EventV2').get()
    # assert 1 == len(events)
    # assert 22 == events[0]['args']['value']
    # contract_instance = web3.eth.contract(
    #     abi=contract1_lib.abi,
    #     address=dispatcher.address,
    #     ContractFactoryClass=Contract)
    # events = contract_instance.pastEvents('EventV1').get()
    # assert 1 == len(events)
    # assert 33 == events[0]['args']['value']
