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
import os
import random
import string

import pytest
from web3.auto import w3

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED, MAX_MINTING_PERIODS, \
    MAX_ALLOWED_LOCKED, ONE_YEAR_IN_SECONDS
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry, InMemoryAllocationRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.utilities.sandbox.blockchain import TesterBlockchain
from nucypher.utilities.sandbox.constants import TESTING_ETH_AIRDROP_AMOUNT


@pytest.mark.slow()
def test_rapid_deployment():
    compiler = SolidityCompiler()
    registry = InMemoryEthereumContractRegistry()
    allocation_registry = InMemoryAllocationRegistry()
    interface = BlockchainDeployerInterface(compiler=compiler,
                                            registry=registry,
                                            provider_uri='tester://pyevm')
    blockchain = TesterBlockchain(interface=interface, airdrop=True, test_accounts=4)
    deployer_address = blockchain.etherbase_account

    deployer = Deployer(blockchain=blockchain,
                        deployer_address=deployer_address)

    # The Big Three (+ Dispatchers)
    deployer.deploy_network_contracts(miner_secret=os.urandom(32),
                                      policy_secret=os.urandom(32))

    # User Escrow Proxy
    deployer.deploy_escrow_proxy(secret=os.urandom(32))

    # Deploy User Escrow
    total_allocations = 100

    all_yall = blockchain.unassigned_accounts
    # Start with some hard-coded cases...
    allocation_data = [{'address': all_yall[1], 'amount': MAX_ALLOWED_LOCKED, 'duration': ONE_YEAR_IN_SECONDS},
                       {'address': all_yall[2], 'amount': MIN_ALLOWED_LOCKED, 'duration': ONE_YEAR_IN_SECONDS*2},
                       {'address': all_yall[3], 'amount': MIN_ALLOWED_LOCKED*100, 'duration': ONE_YEAR_IN_SECONDS*3}]

    # Pile on the rest
    for _ in range(total_allocations - len(allocation_data)):
        random_password = ''.join(random.SystemRandom().choice(string.ascii_uppercase+string.digits) for _ in range(16))
        acct = w3.eth.account.create(random_password)
        beneficiary_address = acct.address
        amount = random.randint(MIN_ALLOWED_LOCKED, MAX_ALLOWED_LOCKED)
        duration = random.randint(MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS*3)
        random_allocation = {'address': beneficiary_address, 'amount': amount, 'duration': duration}
        allocation_data.append(random_allocation)

    deployer.deploy_beneficiary_contracts(allocations=allocation_data, allocation_registry=allocation_registry)
