import pytest

from nkms.blockchain.eth.interfaces import Registrar


#def test_registrar_read_write(tempfile_path):
#    # Test that the file is initally empty and returns an empty dict.
#    should_be_empty = _read_registrar_file(tempfile_path)
#    assert should_be_empty == {}
#
#    # Test that data can be written and read
#    test_data = {'test': 'foobar'}
#    _write_registrar_file(test_data, tempfile_path)
#    out_data = _read_registrar_file(tempfile_path)
#    assert test_data == out_data
#
#    # Test overwrite
#    new_test_data = {'new_test': 'foobar'}
#    _write_registrar_file(new_test_data, tempfile_path)
#    out_data = _read_registrar_file(tempfile_path)
#    assert out_data != test_data and new_test_data == out_data


def test_registrar_object(tempfile_path):
    # Tests everything is as it should be when initially created
    test_registrar = Registrar(registrar_filepath=tempfile_path)
    assert test_registrar._chain_name == 'tester'

    should_be_empty = test_registrar._Registrar__read()
    assert should_be_empty['tester'] == {}

    contains_registrar = Registrar.get_registrars(tempfile_path)
    assert isinstance(contains_registrar['tester'], Registrar)

    # Test contract enrollment and dump_chain
    test_name = 'test_contract'
    test_addr = '0xDEADBEEF'
    test_abi = ['fake', 'data']
    test_registrar.enroll(test_name, test_addr, test_abi)

    chain_data = test_registrar.dump_chain()
    assert test_addr in chain_data
    assert chain_data[test_addr]['name'] == test_name
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

    # Test enroll with same contract name updates contract data
    new_test_addr = '0xBEEFDEAD'
    test_registrar.enroll(test_name, new_test_addr, test_abi)

    test_contract = test_registrar.dump_contract(new_test_addr)
    assert test_contract['addr'] == new_test_addr
    assert test_contract['abi'] == test_abi

    # Test new chain via new registrar object
    new_chain_name = 'not_tester'
    new_chain_registrar = Registrar(chain_name=new_chain_name, registrar_filepath=tempfile_path)
    chains = Registrar.get_registrars(tempfile_path)
    assert new_chain_name not in chains # Not written yet, shouldn't be there

    new_chain_registrar.enroll(new_chain_name, new_test_addr, test_abi)
    updated_chains = Registrar.get_registrars(tempfile_path)
    assert new_chain_name in updated_chains and 'tester' in updated_chains

    with pytest.raises(Registrar.UnknownContract):
        test_registrar.dump_contract('This should not exist')
