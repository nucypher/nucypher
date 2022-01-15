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
from pathlib import Path

import pytest

from nucypher.blockchain.eth.interfaces import BaseContractRegistry
from nucypher.blockchain.eth.registry import LocalContractRegistry, InMemoryContractRegistry


def test_contract_registry(tempfile_path):

    # ABC
    with pytest.raises(TypeError):
        BaseContractRegistry(filepath='test')

    with pytest.raises(BaseContractRegistry.RegistryError):
        bad_registry = LocalContractRegistry(filepath=Path('/fake/file/path/registry.json'))
        bad_registry.search(contract_address='0xdeadbeef')

    # Tests everything is as it should be when initially created
    test_registry = LocalContractRegistry(filepath=tempfile_path)

    assert test_registry.read() == list()
    registry_id = test_registry.id
    assert test_registry.id == registry_id

    # Test contract enrollment and dump_chain
    test_name = 'TestContract'
    test_addr = '0xDEADBEEF'
    test_abi = ['fake', 'data']
    test_version = "some_version"

    test_registry.enroll(contract_name=test_name,
                         contract_address=test_addr,
                         contract_abi=test_abi,
                         contract_version=test_version)

    assert test_registry.id != registry_id
    registry_id = test_registry.id
    assert test_registry.id == registry_id

    # Search by name...
    contract_records = test_registry.search(contract_name=test_name)
    assert len(contract_records) == 1, 'More than one record for {}'.format(test_name)
    assert len(contract_records[0]) == 4, 'Registry record is the wrong length'
    name, version, address, abi = contract_records[0]

    assert name == test_name
    assert address == test_addr
    assert abi == test_abi
    assert version == test_version

    # ...or by address
    contract_record = test_registry.search(contract_address=test_addr)
    name, version, address, abi = contract_record

    assert name == test_name
    assert address == test_addr
    assert abi == test_abi
    assert version == test_version

    # Check that searching for an unknown contract raises
    with pytest.raises(BaseContractRegistry.UnknownContract):
        test_registry.search(contract_name='this does not exist')

    current_dataset = test_registry.read()
    # Corrupt the registry with a duplicate address
    current_dataset.append([test_name, test_addr, test_abi])
    test_registry.write(current_dataset)
    assert test_registry.id != registry_id

    # Check that searching for an unknown contract raises
    with pytest.raises(BaseContractRegistry.InvalidRegistry):
        test_registry.search(contract_address=test_addr)

    # Check id of new registry with the same content
    new_registry = InMemoryContractRegistry()
    new_registry.write(test_registry.read())
    assert new_registry.id == test_registry.id
