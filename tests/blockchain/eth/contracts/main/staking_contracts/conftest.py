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
import pytest
from eth_utils import keccak
from web3.contract import Contract

from nucypher.blockchain.eth.token import NU

@pytest.fixture()
def token(testerchain, deploy_contract):
    # Create an ERC20 token
    token, _ = deploy_contract('NuCypherToken', _totalSupply=int(NU(2 * 10 ** 9, 'NuNit')))
    return token


@pytest.fixture()
def escrow(testerchain, token, deploy_contract):
    creator = testerchain.client.accounts[0]
    # Creator deploys the escrow
    contract, _ = deploy_contract('StakingEscrowForStakingContractMock', token.address)

    # Give some coins to the escrow
    tx = token.functions.transfer(contract.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    return contract


@pytest.fixture()
def policy_manager(testerchain, deploy_contract):
    contract, _ = deploy_contract('PolicyManagerForStakingContractMock')
    return contract


@pytest.fixture()
def staking_interface(testerchain, token, escrow, policy_manager, deploy_contract):
    # Creator deploys the staking interface
    contract, _ = deploy_contract(
        'StakingInterface', token.address, escrow.address, policy_manager.address)
    return contract


@pytest.fixture()
def router(testerchain, staking_interface, deploy_contract):
    secret = os.urandom(32)
    secret_hash = keccak(secret)
    contract, _ = deploy_contract('StakingInterfaceRouter', staking_interface.address, secret_hash)
    return contract


@pytest.fixture()
def preallocation_escrow(testerchain, token, router, deploy_contract):
    creator = testerchain.client.accounts[0]
    user = testerchain.client.accounts[1]

    contract, _ = deploy_contract('PreallocationEscrow', router.address, token.address)

    # Transfer ownership
    tx = contract.functions.transferOwnership(user).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    return contract


@pytest.fixture()
def preallocation_escrow_interface(testerchain, staking_interface, preallocation_escrow):
    return testerchain.client.get_contract(
        abi=staking_interface.abi,
        address=preallocation_escrow.address,
        ContractFactoryClass=Contract)
