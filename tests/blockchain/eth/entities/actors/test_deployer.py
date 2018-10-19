import os
import random
import string

import pytest
from web3.auto import w3

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.constants import MIN_LOCKED_PERIODS, MIN_ALLOWED_LOCKED, MAX_MINTING_PERIODS, \
    MAX_ALLOWED_LOCKED


@pytest.mark.slow()
def test_rapid_deployment(testerchain):
    deployer = Deployer(blockchain=testerchain)
    deployer_address, *all_yall = deployer.blockchain.interface.w3.eth.accounts

    # The Big Three (+ Dispatchers)
    deployer.deploy_network_contracts(miner_secret=os.urandom(32),
                                      policy_secret=os.urandom(32))

    # User Escrow Proxy
    deployer.deploy_escrow_proxy(secret=os.urandom(32))

    # Deploy User Escrow
    total_allocations = 100

    # Start with some hard-coded cases...
    allocation_data = [{'address': all_yall[1], 'amount': MAX_ALLOWED_LOCKED, 'periods': MIN_LOCKED_PERIODS},
                       {'address': all_yall[2], 'amount': MIN_ALLOWED_LOCKED, 'periods': MIN_LOCKED_PERIODS},
                       {'address': all_yall[7], 'amount': MIN_ALLOWED_LOCKED*100, 'periods': MAX_MINTING_PERIODS*3}]

    # Pile on the rest
    for _ in range(total_allocations - len(allocation_data)):
        random_password = ''.join(random.SystemRandom().choice(string.ascii_uppercase+string.digits) for _ in range(16))
        acct = w3.eth.account.create(random_password)
        beneficiary_address = acct.address
        amount = random.randint(MIN_ALLOWED_LOCKED, MAX_ALLOWED_LOCKED)
        duration = random.randint(MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS*3)
        random_allocation = {'address': beneficiary_address, 'amount': amount, 'periods': duration}
        allocation_data.append((random_allocation))

    deployer.deploy_beneficiary_contracts(allocations=allocation_data)

