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
from web3.contract import Contract

from nucypher.blockchain.eth.deployers import DispatcherDeployer


@pytest.fixture()
def escrow(testerchain):
    escrow, _ = testerchain.deploy_contract('StakingEscrowForAdjudicatorMock')
    return escrow


@pytest.fixture(params=[False, True])
def adjudicator_contract(testerchain, escrow, request, slashing_economics):
    contract, _ = testerchain.deploy_contract(
        'Adjudicator',
        escrow.address,
        *slashing_economics.deployment_parameters)

    if request.param:
        secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
        secret_hash = testerchain.w3.keccak(secret)
        dispatcher, _ = testerchain.deploy_contract('Dispatcher', contract.address, secret_hash)

        # Deploy second version of the government contract
        contract = testerchain.w3.eth.contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    return contract
