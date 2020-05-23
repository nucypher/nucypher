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

from nucypher.blockchain.eth.constants import PREALLOCATION_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.registry import IndividualAllocationRegistry
from nucypher.config.constants import TEMPORARY_DOMAIN


def test_individual_allocation_registry(get_random_checksum_address,
                                        test_registry,
                                        tempfile_path,
                                        testerchain,
                                        test_registry_source_manager):

    factory = testerchain.get_contract_factory(contract_name=PREALLOCATION_ESCROW_CONTRACT_NAME)
    allocation_contract_abi = factory.abi

    beneficiary = get_random_checksum_address()
    contract_address = get_random_checksum_address()
    allocation_registry = IndividualAllocationRegistry(beneficiary_address=beneficiary,
                                                       contract_address=contract_address,
                                                       network=TEMPORARY_DOMAIN)

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

    allocation_registry = IndividualAllocationRegistry.from_allocation_file(filepath=tempfile_path,
                                                                            network=TEMPORARY_DOMAIN)
    assert registry_data == allocation_registry.read()
