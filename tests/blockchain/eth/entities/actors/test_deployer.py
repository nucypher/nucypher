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

import random
import string

import pytest
from web3.auto import w3

from nucypher.blockchain.eth.actors import Administrator
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.crypto.powers import TransactingPower
# Prevents TesterBlockchain to be picked up by py.test as a test class
from nucypher.utilities.sandbox.blockchain import TesterBlockchain as _TesterBlockchain
from nucypher.utilities.sandbox.constants import (
    ONE_YEAR_IN_SECONDS,
    NUMBER_OF_ALLOCATIONS_IN_TESTS,
    INSECURE_DEVELOPMENT_PASSWORD
)


@pytest.mark.slow()
@pytest.mark.usefixtures('testerchain')
def test_rapid_deployment(token_economics, test_registry):
    compiler = SolidityCompiler()
    allocation_registry = InMemoryAllocationRegistry()

    blockchain = _TesterBlockchain(eth_airdrop=False,
                                   test_accounts=4,
                                   compiler=compiler)

    # TODO: #1092 - TransactingPower
    blockchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                    account=blockchain.etherbase_account)
    blockchain.transacting_power.activate()
    deployer_address = blockchain.etherbase_account

    deployer = Administrator(deployer_address=deployer_address,
                             registry=test_registry)

    secrets = dict()
    for deployer_class in deployer.upgradeable_deployer_classes:
        secrets[deployer_class.contract_name] = INSECURE_DEVELOPMENT_PASSWORD

    deployer.deploy_network_contracts(secrets=secrets, emitter=StdoutEmitter())

    all_yall = blockchain.unassigned_accounts

    # Start with some hard-coded cases...
    allocation_data = [{'staker_address': all_yall[1],
                        'amount': token_economics.maximum_allowed_locked,
                        'lock_periods': ONE_YEAR_IN_SECONDS},

                       {'staker_address': all_yall[2],
                        'amount': token_economics.minimum_allowed_locked,
                        'lock_periods': ONE_YEAR_IN_SECONDS*2},

                       {'staker_address': all_yall[3],
                        'amount': token_economics.minimum_allowed_locked*100,
                        'lock_periods': ONE_YEAR_IN_SECONDS*3}
                       ]

    # Pile on the rest
    for _ in range(NUMBER_OF_ALLOCATIONS_IN_TESTS - len(allocation_data)):
        random_password = ''.join(random.SystemRandom().choice(string.ascii_uppercase+string.digits) for _ in range(16))
        acct = w3.eth.account.create(random_password)
        beneficiary_address = acct.address
        amount = random.randint(token_economics.minimum_allowed_locked, token_economics.maximum_allowed_locked)
        duration = random.randint(token_economics.minimum_locked_periods*ONE_YEAR_IN_SECONDS,
                                  (token_economics.maximum_locked_periods*ONE_YEAR_IN_SECONDS)*3)
        random_allocation = {'staker_address': beneficiary_address, 'amount': amount, 'lock_periods': duration}
        allocation_data.append(random_allocation)

    deployer.deploy_beneficiary_contracts(allocations=allocation_data, allocation_registry=allocation_registry)
