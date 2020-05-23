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

from nucypher.blockchain.economics import EconomicsFactory


@pytest.mark.usefixtures('agency')
def test_retrieving_from_blockchain(token_economics, test_registry):

    economics = EconomicsFactory.get_economics(registry=test_registry)

    assert economics.staking_deployment_parameters == token_economics.staking_deployment_parameters
    assert economics.slashing_deployment_parameters == token_economics.slashing_deployment_parameters
    assert economics.worklock_deployment_parameters == token_economics.worklock_deployment_parameters
