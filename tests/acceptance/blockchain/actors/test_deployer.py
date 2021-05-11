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
import random

from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.actors import ContractAdministrator
from nucypher.blockchain.eth.signers.software import Web3Signer
from tests.constants import NUMBER_OF_ALLOCATIONS_IN_TESTS

# Prevents TesterBlockchain to be picked up by py.test as a test class
from tests.utils.blockchain import TesterBlockchain as _TesterBlockchain


@pytest.mark.usefixtures('testerchain')
def test_rapid_deployment(token_economics, test_registry, temp_dir_path, get_random_checksum_address):

    blockchain = _TesterBlockchain(eth_airdrop=False, test_accounts=4)

    deployer_address = blockchain.etherbase_account
    deployer_power = TransactingPower(signer=Web3Signer(blockchain.client), account=deployer_address)

    administrator = ContractAdministrator(transacting_power=deployer_power,
                                          domain=TEMPORARY_DOMAIN,
                                          registry=test_registry)
    blockchain.bootstrap_network(registry=test_registry)

    all_yall = blockchain.unassigned_accounts

    # Start with some hard-coded cases...
    allocation_data = [{'checksum_address': all_yall[1],
                        'amount': token_economics.maximum_allowed_locked,
                        'lock_periods': token_economics.minimum_locked_periods},

                       {'checksum_address': all_yall[2],
                        'amount': token_economics.minimum_allowed_locked,
                        'lock_periods': token_economics.minimum_locked_periods},

                       {'checksum_address': all_yall[3],
                        'amount': token_economics.minimum_allowed_locked*100,
                        'lock_periods': token_economics.minimum_locked_periods},
                       ]

    # Pile on the rest
    for _ in range(NUMBER_OF_ALLOCATIONS_IN_TESTS - len(allocation_data)):
        checksum_address = get_random_checksum_address()
        amount = random.randint(token_economics.minimum_allowed_locked, token_economics.maximum_allowed_locked)
        duration = random.randint(token_economics.minimum_locked_periods, token_economics.maximum_rewarded_periods)
        random_allocation = {'checksum_address': checksum_address, 'amount': amount, 'lock_periods': duration}
        allocation_data.append(random_allocation)

    filepath = temp_dir_path / "allocations.json"
    with open(filepath, 'w') as f:
        json.dump(allocation_data, f)

    minimum, default, maximum = 10, 20, 30
    administrator.set_fee_rate_range(minimum, default, maximum)
