import json
import pytest

from nkms.blockchain.eth.interfaces import (
    Registrar, _write_registrar_file, _read_registrar_file
)


def test_registrar_read_write(tempfile_path):
    # Test that the file is initally empty and returns an empty dict.
    should_be_empty = _read_registrar_data(tempfile_path)
    assert should_be_empty == {}

    # Test that data can be written and read
    test_data = {'test': 'foobar'}
    _write_registrar_file(test_data, tempfile_path)
    out_data = _read_registrar_file(tempfile_path)
    assert test_data == out_data

    # Test overwrite
    new_test_data = {'new_test': 'foobar'}
    _write_registrar_file(new_test_data, tempfile_path)
    out_data = _read_registrar_file(tempfile_path)
    assert out_data != test_data and new_test_data == out_data


def test_registrar_object(tempfile_path):
    # Tests everything is as it should be when initially created
    test_registrar = Registrar(registrar_filepath=tempfile_path)
    assert test_registrar._chain_name == 'tester'

    should_be_empty = _read_registrar_file(tempfile_path)
    assert should_be_empty == {}

    should_also_be_empty = Registrar.get_chains(tempfile_path)
    assert should_also_be_empty = {}

    # Test contract enrollment and get_chain_data
    test_name = 'test_contract'
    test_addr = '0xDEADBEEF'
    test_abi = ['fake', 'data']
    test_registrar.enroll(test_name, test_addr, test_abi)

    chain_data = test_registrar.get_chain_data()
    assert test_name in chain_data
    assert chain_data[test_name]['addr'] == test_addr
    assert chain_data[test_name]['abi'] == test_abi

    # Test get_contract_data via identifier
    contract_by_name = test_registrar.get_contract_data(test_name)
    assert contract_by_name['addr'] == test_addr
    assert contract_by_name['abi'] == test_abi

    contract_by_addr = test_registrar.get_contract_data(test_addr)
    assert contract_by_addr['addr'] == test_addr
    assert contract_by_addr['abi'] == test_abi

    assert contract_by_name == contract_by_addr

    # Test enroll with same contract name updates contract data
    new_test_addr = '0xBEEFDEAD'
    test_registrar.enroll(test_name, new_test_addr, test_abi)

    test_contract = test_registrar.get_contract_data(test_name)
    assert test_contract['addr'] == new_test_addr
    assert test_contract['abi'] == test_abi

    # Test new chain via new registrar object
    new_chain_name = 'not_tester'
    new_chain_registrar = Registrar(chain_name=new_chain_name, registrar_filepath=tempfile_path)
    chains = Registrar.get_chains(tempfile_path)
    assert new_chain_name not in chains # Not written yet, shouldn't be there

    with pytest.raises(KeyError):
        new_chain_registrar.get_chain_data()

    new_chain_registrar.enroll(test_name, test_addr, test_abi)
    updated_chains = Registrar.get_chains(tempfile_path)
    assert new_chain_name in chains and 'tester' in chains

    # Test NoKnownContract error
    with pytest.raises(Registrar.NoKnownContract):
        test_registrar.get_contract_data('This should not exist')
