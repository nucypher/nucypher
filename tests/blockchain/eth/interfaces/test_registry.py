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

import json
import pytest

from nucypher.blockchain.eth.deployers import PreallocationEscrowDeployer
from nucypher.blockchain.eth.interfaces import BaseContractRegistry
from nucypher.blockchain.eth.registry import LocalContractRegistry, IndividualAllocationRegistry


@pytest.fixture(autouse=True, scope='module')
def patch_individual_allocation_fetch_latest_publication(_patch_individual_allocation_fetch_latest_publication):
    pass


def test_contract_registry(tempfile_path):

    # ABC
    with pytest.raises(TypeError):
        BaseContractRegistry(filepath='test')

    with pytest.raises(BaseContractRegistry.RegistryError):
        bad_registry = LocalContractRegistry(filepath='/fake/file/path/registry.json')
        bad_registry.search(contract_address='0xdeadbeef')

    # Tests everything is as it should be when initially created
    test_registry = LocalContractRegistry(filepath=tempfile_path)

    assert test_registry.read() == list()

    # Test contract enrollment and dump_chain
    test_name = 'TestContract'
    test_addr = '0xDEADBEEF'
    test_abi = ['fake', 'data']
    test_version = "some_version"

    test_registry.enroll(contract_name=test_name,
                         contract_address=test_addr,
                         contract_abi=test_abi,
                         contract_version=test_version)

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

    # Check that searching for an unknown contract raises
    with pytest.raises(BaseContractRegistry.InvalidRegistry):
        test_registry.search(contract_address=test_addr)


def test_individual_allocation_registry(get_random_checksum_address, test_registry, tempfile_path):
    empty_allocation_escrow_deployer = PreallocationEscrowDeployer(registry=test_registry)
    allocation_contract_abi = empty_allocation_escrow_deployer.get_contract_abi()

    beneficiary = get_random_checksum_address()
    contract_address = get_random_checksum_address()
    allocation_registry = IndividualAllocationRegistry(beneficiary_address=beneficiary,
                                                       contract_address=contract_address)

    registry_data = allocation_registry.read()
    assert len(registry_data) == 1

    assert allocation_registry.search(beneficiary_address=beneficiary) == [contract_address, allocation_contract_abi]
    assert allocation_registry.search(contract_address=contract_address) == [beneficiary, allocation_contract_abi]

    # Check that searching for an unknown beneficiary or unknown contract raises
    with pytest.raises(IndividualAllocationRegistry.UnknownBeneficiary):
        allocation_registry.search(beneficiary_address=get_random_checksum_address())

    with pytest.raises(IndividualAllocationRegistry.UnknownContract):
        allocation_registry.search(contract_address=get_random_checksum_address())

    # Check that it gets the same data if using a file to create the allocation registry
    individual_allocation_file_data = {
        'beneficiary_address': beneficiary,
        'contract_address': contract_address
    }
    with open(tempfile_path, 'w') as outfile:
        json.dump(individual_allocation_file_data, outfile)

    allocation_registry = IndividualAllocationRegistry.from_allocation_file(filepath=tempfile_path)
    assert registry_data == allocation_registry.read()

