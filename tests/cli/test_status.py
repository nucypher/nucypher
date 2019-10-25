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
import re

import pytest

from nucypher.blockchain.eth.agents import (
    PolicyManagerAgent,
    StakingEscrowAgent,
    AdjudicatorAgent,
    NucypherTokenAgent,
    ContractAgency
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.cli.status import status
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI, MOCK_REGISTRY_FILEPATH


def test_nucypher_status_network(click_runner, testerchain, test_registry, agency):

    network_command = ('network',
                       '--registry-filepath', MOCK_REGISTRY_FILEPATH,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, network_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=test_registry)

    agents = (token_agent, staking_agent, policy_agent, adjudicator_agent)
    for agent in agents:
        contract_regex = f"^{agent.contract_name} \\.+ {agent.contract_address}"
        assert re.search(contract_regex, result.output, re.MULTILINE)

    assert re.search(f"^Provider URI \\.+ {TEST_PROVIDER_URI}", result.output, re.MULTILINE)
    assert re.search(f"^Registry \\.+ {MOCK_REGISTRY_FILEPATH}", result.output, re.MULTILINE)
    assert re.search(f"^Current Period \\.+ {staking_agent.get_current_period()}", result.output, re.MULTILINE)


def test_nucypher_status_stakers(click_runner, testerchain, test_registry, agency, stakers):

    # Get all stakers info
    stakers_command = ('stakers',
                       '--registry-filepath', MOCK_REGISTRY_FILEPATH,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    # TODO: Use regex matching instead of this
    assert re.search(f"^Current period: {staking_agent.get_current_period()}", result.output, re.MULTILINE)
    for staker in stakers:
        assert re.search(f"^{staker.checksum_address}", result.output, re.MULTILINE)

    # Get info of only one staker
    some_dude = random.choice(stakers)
    staking_address = some_dude.checksum_address
    stakers_command = ('stakers', '--staking-address', staking_address,
                       '--registry-filepath', MOCK_REGISTRY_FILEPATH,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    owned_tokens = NU.from_nunits(staking_agent.owned_tokens(staking_address))
    locked_tokens = NU.from_nunits(staking_agent.get_locked_tokens(staking_address))

    assert re.search(f"^Current period: {staking_agent.get_current_period()}", result.output, re.MULTILINE)
    assert re.search(r"Worker:\s+" + some_dude.worker_address, result.output, re.MULTILINE)
    assert re.search(r"Owned:\s+" + str(round(owned_tokens, 2)), result.output, re.MULTILINE)
    assert re.search(r"Staked: " + str(round(locked_tokens, 2)), result.output, re.MULTILINE)


