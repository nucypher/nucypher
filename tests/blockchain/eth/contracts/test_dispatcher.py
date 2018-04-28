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
    contract1_lib, _ = chain.provider.deploy_contract('ContractV1', 1)
    contract2_lib, _ = chain.provider.deploy_contract('ContractV2', 1)
    contract3_lib, _ = chain.provider.deploy_contract('ContractV3', 2)
    contract2_bad_lib, _ = chain.provider.deploy_contract('ContractV2Bad')
    dispatcher, _ = chain.provider.deploy_contract('Dispatcher', contract1_lib.address)

    upgrades = dispatcher.events.Upgraded.createFilter(fromBlock=0)
    assert dispatcher.functions.target().call() == contract1_lib.address

    events = upgrades.get_all_entries()
    assert 1 == len(events)

    event_args = events[0]['args']
    assert '0x' + '0' * 40 == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1, ContractV2 or ContractV3 ABI
    contract_instance = web3.eth.contract(
        abi=contract_interface.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Only owner can change target address for dispatcher
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract2_lib.address).transact({'from': account})
        chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract1_lib.address

    # Check values before upgrade
    assert contract_instance.functions.getStorageValue().call() == 1
    assert contract_instance.functions.returnValue().call() == 10
    tx =  contract_instance.functions.setStorageValue(5).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStorageValue().call() == 5
    tx =  contract_instance.functions.pushArrayValue(12).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getArrayValueLength().call() == 1
    assert contract_instance.functions.getArrayValue(0).call() == 12
    tx =  contract_instance.functions.pushArrayValue(232).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getArrayValueLength().call() == 2
    assert contract_instance.functions.getArrayValue(1).call() == 232
    tx =  contract_instance.functions.setMappingValue(14, 41).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getMappingValue(14).call() == 41
    tx =  contract_instance.functions.pushStructureValue1(3).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureValue1(0).call() == 3
    tx =  contract_instance.functions.pushStructureArrayValue1(0, 11).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureArrayValue1(0, 0).call() == 11
    tx =  contract_instance.functions.pushStructureValue2(4).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureValue2(0).call() == 4
    tx =  contract_instance.functions.pushStructureArrayValue2(0, 12).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureArrayValue2(0, 0).call() == 12

    # Can't upgrade to bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract2_bad_lib.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract1_lib.address

    # Upgrade contract
    tx =  dispatcher.functions.upgrade(contract2_lib.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract2_lib.address

    events = upgrades.get_all_entries()
    assert 2 == len(events)

    event_args = events[1]['args']
    assert contract1_lib.address == event_args['from']
    assert contract2_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Check values after upgrade
    assert contract_instance.functions.returnValue().call() == 20
    assert contract_instance.functions.getStorageValue().call() == 5
    tx =  contract_instance.functions.setStorageValue(5).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStorageValue().call() == 10
    assert contract_instance.functions.getArrayValueLength().call() == 2
    assert contract_instance.functions.getArrayValue(0).call() == 12
    assert contract_instance.functions.getArrayValue(1).call() == 232
    tx =  contract_instance.functions.setMappingValue(13, 31).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getMappingValue(14).call() == 41
    assert contract_instance.functions.getMappingValue(13).call() == 31
    tx =  contract_instance.functions.pushStructureValue1(4).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureValue1(0).call() == 3
    assert contract_instance.functions.getStructureValue1(1).call() == 4
    tx =  contract_instance.functions.pushStructureArrayValue1(0, 12).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureArrayValue1(0, 0).call() == 11
    assert contract_instance.functions.getStructureArrayValue1(0, 1).call() == 12
    tx =  contract_instance.functions.pushStructureValue2(5).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureValue2(0).call() == 4
    assert contract_instance.functions.getStructureValue2(1).call() == 5
    tx =  contract_instance.functions.pushStructureArrayValue2(0, 13).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureArrayValue2(0, 0).call() == 12
    assert contract_instance.functions.getStructureArrayValue2(0, 1).call() == 13

    # Changes ABI to ContractV2 for using additional methods
    contract_instance = web3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Check new method and finish upgrade method
    assert contract_instance.functions.storageValueToCheck().call() == 1
    tx =  contract_instance.functions.setStructureValueToCheck2(0, 55).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStructureValueToCheck2(0).call() == 55

    # Can't downgrade to first version due to storage
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract1_lib.address).transact({'from': creator})
        chain.wait_for_receipt(tx)

    # And can't upgrade to bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract2_bad_lib.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract2_lib.address

    rollbacks = dispatcher.events.RolledBack.createFilter(fromBlock=0)

    # But can rollback
    tx = dispatcher.functions.rollback().transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract1_lib.address
    assert contract_instance.functions.getArrayValueLength().call() == 2
    assert contract_instance.functions.getArrayValue(0).call() == 12
    assert contract_instance.functions.getArrayValue(1).call() == 232
    assert contract_instance.functions.getStorageValue().call() == 1
    tx =  contract_instance.functions.setStorageValue(5).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert contract_instance.functions.getStorageValue().call() == 5

    events = rollbacks.get_all_entries()

    assert 1 == len(events)
    event_args = events[0]['args']
    assert contract2_lib.address == event_args['from']
    assert contract1_lib.address == event_args['to']
    assert creator == event_args['owner']

    # Can't upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx =  dispatcher.functions.upgrade(contract2_bad_lib.address).transact({'from': creator})
        chain.wait_for_receipt(tx)
    assert dispatcher.functions.target().call() == contract1_lib.address

    # Check dynamically sized value
    # TODO uncomment after fixing dispatcher
    # tx =  contract_instance.functions.setDynamicallySizedValue('Hola').transact({'from': creator})
    # chain.wait_for_receipt(tx)
    # assert contract_instance.functions.getDynamicallySizedValue().call() == 'Hola'

    # # Create Event
    # contract_instance = web3.eth.contract(
    #     abi=contract1_lib.abi,
    #     address=dispatcher.address,
    #     ContractFactoryClass=Contract)
    # test_events = contract_instance.events.EventV1.createFilter(fromBlock=0)
    # events = test_events.get_all_entries()
    # tx =  contract_instance.functions.createEvent(33).transact({'from': creator})
    # chain.wait_for_receipt(tx)
    # assert 1 == len(events)
    # assert 33 == events[0]['args']['value']

    # Upgrade to version 3
    tx =  dispatcher.functions.upgrade(contract2_lib.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    tx =  dispatcher.functions.upgrade(contract3_lib.address).transact({'from': creator})
    chain.wait_for_receipt(tx)
    contract_instance = web3.eth.contract(
        abi=contract2_lib.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)
    assert dispatcher.functions.target().call() == contract3_lib.address
    assert contract_instance.functions.returnValue().call() == 20
    assert contract_instance.functions.getStorageValue().call() == 5
    assert contract_instance.functions.getArrayValueLength().call() == 2
    assert contract_instance.functions.getArrayValue(0).call() == 12
    assert contract_instance.functions.getArrayValue(1).call() == 232
    assert contract_instance.functions.getMappingValue(14).call() == 41
    assert contract_instance.functions.getMappingValue(13).call() == 31
    assert contract_instance.functions.getStorageValue().call() == 5
    assert contract_instance.functions.getStructureValue1(0).call() == 3
    assert contract_instance.functions.getStructureValue1(1).call() == 4
    assert contract_instance.functions.getStructureArrayValue1(0, 0).call() == 11
    assert contract_instance.functions.getStructureArrayValue1(0, 1).call() == 12
    assert contract_instance.functions.getStructureValue2(0).call() == 4
    assert contract_instance.functions.getStructureValue2(1).call() == 5
    assert contract_instance.functions.getStructureArrayValue2(0, 0).call() == 12
    assert contract_instance.functions.getStructureArrayValue2(0, 1).call() == 13
    assert contract_instance.functions.getStructureValueToCheck2(0).call() == 55
    assert contract_instance.functions.storageValueToCheck().call() == 2

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
    tx =  contract_instance.functions.createEvent(22).transact({'from': creator})
    chain.wait_for_receipt(tx)
    test_eventv2_log = contract_instance.events.EventV2.createFilter(fromBlock=0)
    events = test_eventv2_log.get_all_entries()

    assert 1 == len(events)
    assert 22 == events[0]['args']['value']

    # TODO
    # contract_instance = web3.eth.contract(
    #     abi=contract1_lib.abi,
    #     address=dispatcher.address,
    #     ContractFactoryClass=Contract)
    #
    # test_eventv1_log = contract_instance.events.EventV1.createFilter(fromBlock=0)
    # events = test_eventv1_log.get_all_entries()
    #
    # assert 1 == len(events)
    # assert 33 == events[0]['args']['value']
