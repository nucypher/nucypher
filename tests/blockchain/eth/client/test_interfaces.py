import pytest

from nucypher.blockchain.eth.interfaces import EthereumContractRegistrar


def test_registrar_object(tempfile_path):
    # Tests everything is as it should be when initially created
    test_registrar = EthereumContractRegistrar(registrar_filepath=tempfile_path)
    assert test_registrar._chain_name == 'tester'

    should_be_empty = test_registrar._EthereumContractRegistrar__read()
    assert should_be_empty['tester'] == {}

    contains_registrar = EthereumContractRegistrar.get_registrars(tempfile_path)
    assert isinstance(contains_registrar['tester'], EthereumContractRegistrar)

    # Test contract enrollment and dump_chain
    test_addr = '0xDEADBEEF'
    test_abi = ['fake', 'data']
    test_registrar.enroll(test_addr, test_abi)

    chain_data = test_registrar.dump_chain()
    assert test_addr in chain_data
    assert chain_data[test_addr]['addr'] == test_addr
    assert chain_data[test_addr]['abi'] == test_abi

    # Test dump_contract via identifier
    contract_by_name = test_registrar.dump_contract(test_addr)
    assert contract_by_name['addr'] == test_addr
    assert contract_by_name['abi'] == test_abi

    contract_by_addr = test_registrar.dump_contract(test_addr)
    assert contract_by_addr['addr'] == test_addr
    assert contract_by_addr['abi'] == test_abi

    assert contract_by_name == contract_by_addr

    # Test enrolling a dispatcher
    new_test_addr = '0xTESTDISPATCHER'
    new_test_abi = ['dispatch', 'test', 'info']
    new_test_name = 'TestNameDispatcher'
    new_test_target_addr = '0xTARGET'
    test_registrar.enroll(new_test_addr, new_test_abi, new_test_name, new_test_target_addr)

    contract_by_name = test_registrar.lookup_contract(new_test_name)
    assert contract_by_name['addr'] == new_test_addr
    assert contract_by_name['abi'] == new_test_abi
    assert contract_by_name['name'] == new_test_name
    assert contract_by_name['target_addr'] == new_test_target_addr

    # Check that it raises an error
    with pytest.raises(EthereumContractRegistrar.UnknownContract):
        test_registrar.lookup_contract('this will not exist')

    # Test new chain via new registrar object
    new_chain_name = 'not_tester'
    new_chain_registrar = EthereumContractRegistrar(chain_name=new_chain_name, registrar_filepath=tempfile_path)
    chains = EthereumContractRegistrar.get_registrars(tempfile_path)
    assert new_chain_name not in chains # Not written yet, shouldn't be there

    new_chain_registrar.enroll(new_test_addr, test_abi)
    updated_chains = EthereumContractRegistrar.get_registrars(tempfile_path)
    assert new_chain_name in updated_chains and 'tester' in updated_chains

    with pytest.raises(EthereumContractRegistrar.UnknownContract):
        test_registrar.dump_contract('This should not exist')
