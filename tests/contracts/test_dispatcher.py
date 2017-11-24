import pytest
from ethereum.tester import TransactionFailed
from populus.contracts.contract import PopulusContract


def test_dispatcher(web3, chain):
    """
    These are tests for Dispatcher taken from github:
    https://github.com/willjgriff/solidity-playground/blob/master/Upgradable/ByzantiumUpgradable/test/UpgradableContractProxyTest.js
    but some of the tests are converted from javascript to python
    """

    creator = web3.eth.accounts[1]
    account = web3.eth.accounts[0]

    # Load contract interface
    # contract_interface = chain.provider.get_base_contract_factory('ContractInterface')
    contract_interface = chain.provider.get_base_contract_factory('ContractV1')

    # Deploy contracts and dispatcher for them
    contract1_lib, _ = chain.provider.get_or_deploy_contract('ContractV1')
    contract2_lib, _ = chain.provider.get_or_deploy_contract('ContractV2')
    dispatcher, _ = chain.provider.get_or_deploy_contract(
            'Dispatcher', deploy_args=[contract1_lib.address],
            deploy_transaction={'from': creator})
    # assert dispatcher.call().target().lower() == contract1_lib.address

    # Assign dispatcher address as contract.
    # In addition to the interface can be used ContractV1 or ContractV2 abi
    contract_instance = web3.eth.contract(
        contract_interface.abi,
        dispatcher.address,
        ContractFactoryClass=PopulusContract)

    # Only owner can change target address for dispatcher
    with pytest.raises(TransactionFailed):
        tx = dispatcher.transact({'from': account}).upgrade(contract2_lib.address)
        chain.wait.for_receipt(tx)
    assert dispatcher.call().target().lower() == contract1_lib.address

    # Check return value before and after upgrade
    assert contract_instance.call().returnValue() == 10
    tx = dispatcher.transact({'from': creator}).upgrade(contract2_lib.address)
    chain.wait.for_receipt(tx)
    assert dispatcher.call().target().lower() == contract2_lib.address
    assert contract_instance.call().returnValue() == 20

    # Check storage value for 2 versions
    tx = contract_instance.transact().setStorageValue(5)
    chain.wait.for_receipt(tx)
    tx = contract_instance.transact().getStorageValue()
    chain.wait.for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 10
    tx = dispatcher.transact({'from': creator}).upgrade(contract1_lib.address)
    chain.wait.for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 10
    tx = contract_instance.transact().setStorageValue(5)
    chain.wait.for_receipt(tx)
    assert contract_instance.call().getStorageValue() == 5

    # Check dynamically sized value
    # TODO uncomment after fixing dispatcher
    # tx = contract_instance.transact().setDynamicallySizedValue('Hola')
    # chain.wait.for_receipt(tx)
    # assert contract_instance.call().getDynamicallySizedValue() == 'Hola'
