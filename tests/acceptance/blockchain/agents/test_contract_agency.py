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
from decimal import Decimal, InvalidOperation

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.token import NU


def test_get_agent_with_different_registries(application_economics, agency, test_registry, agency_local_registry):
    # Get agents using same registry instance
    staking_agent_1 = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    staking_agent_2 = ContractAgency.get_agent(PREApplicationAgent, registry=test_registry)
    assert staking_agent_2.registry_str == staking_agent_1.registry_str == str(test_registry)
    assert staking_agent_2 is staking_agent_1

    # Same content but different classes of registries
    staking_agent_2 = ContractAgency.get_agent(PREApplicationAgent, registry=agency_local_registry)
    assert staking_agent_2.registry_str == str(test_registry)
    assert staking_agent_2 is staking_agent_1
