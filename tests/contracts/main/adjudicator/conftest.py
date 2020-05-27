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

import pytest
from web3.contract import Contract

from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture()
def escrow(testerchain, deploy_contract, mock_transacting_power_activation):
    mock_transacting_power_activation(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)
    escrow, _ = deploy_contract('StakingEscrowForAdjudicatorMock')
    return escrow


@pytest.fixture(params=[False, True])
def adjudicator(testerchain, escrow, request, token_economics, deploy_contract):
    contract, _ = deploy_contract(
        'Adjudicator',
        escrow.address,
        *token_economics.slashing_deployment_parameters)

    if request.param:
        dispatcher, _ = deploy_contract('Dispatcher', contract.address)

        # Deploy second version of the government contract
        contract = testerchain.client.get_contract(
            abi=contract.abi,
            address=dispatcher.address,
            ContractFactoryClass=Contract)

    return contract
