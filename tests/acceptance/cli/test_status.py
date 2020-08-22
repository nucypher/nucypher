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

from nucypher.blockchain.eth.agents import (
    AdjudicatorAgent,
    ContractAgency,
    NucypherTokenAgent,
    PolicyManagerAgent,
    StakingEscrowAgent
)
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.status import status
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import FEE_RATE_RANGE, TEST_PROVIDER_URI


def test_nucypher_status_network(click_runner, testerchain, agency_local_registry):

    network_command = ('network',
                       '--registry-filepath', agency_local_registry.filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, network_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=agency_local_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=agency_local_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=agency_local_registry)

    agents = (token_agent, staking_agent, policy_agent, adjudicator_agent)
    for agent in agents:
        contract_regex = f"^{agent.contract_name} \\.+ {agent.contract_address}"
        assert re.search(contract_regex, result.output, re.MULTILINE)

    assert re.search(f"^Provider URI \\.+ {TEST_PROVIDER_URI}", result.output, re.MULTILINE)
    assert re.search(f"^Current Period \\.+ {staking_agent.get_current_period()}", result.output, re.MULTILINE)


def test_nucypher_status_stakers(click_runner, agency_local_registry, stakers):

    # Get all stakers info
    stakers_command = ('stakers',
                       '--registry-filepath', agency_local_registry.filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)

    # TODO: Use regex matching instead of this
    assert re.search(f"^Current period: {staking_agent.get_current_period()}", result.output, re.MULTILINE)
    for staker in stakers:
        assert re.search(f"^{staker.checksum_address}", result.output, re.MULTILINE)

    # Get info of only one staker
    some_dude = random.choice(stakers)
    staking_address = some_dude.checksum_address
    stakers_command = ('stakers', '--staking-address', staking_address,
                       '--registry-filepath', agency_local_registry.filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    owned_tokens = NU.from_nunits(staking_agent.owned_tokens(staking_address))
    current_locked_tokens = NU.from_nunits(staking_agent.get_locked_tokens(staking_address))
    next_locked_tokens = NU.from_nunits(staking_agent.get_locked_tokens(staking_address, 1))

    assert re.search(f"^Current period: {staking_agent.get_current_period()}", result.output, re.MULTILINE)
    assert re.search(r"Worker:\s+" + some_dude.worker_address, result.output, re.MULTILINE)
    assert re.search(r"Owned:\s+" + str(round(owned_tokens, 2)), result.output, re.MULTILINE)
    assert re.search(r"Staked in current period: " + str(round(current_locked_tokens, 2)), result.output, re.MULTILINE)
    assert re.search(r"Staked in next period: " + str(round(next_locked_tokens, 2)), result.output, re.MULTILINE)
    _minimum, default, _maximum = FEE_RATE_RANGE
    assert f"Min fee rate: {default} wei" in result.output


def test_nucypher_status_fee_range(click_runner, agency_local_registry, stakers):

    # Get information about global fee range (minimum rate, default rate, maximum rate)
    stakers_command = ('fee-range',
                       '--registry-filepath', agency_local_registry.filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0
    minimum, default, maximum = FEE_RATE_RANGE
    assert f"{minimum} wei" in result.output
    assert f"{default} wei" in result.output
    assert f"{maximum} wei" in result.output


def test_nucypher_status_locked_tokens(click_runner, testerchain, agency_local_registry, stakers):

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=agency_local_registry)
    # All workers make a commitment
    for ursula in testerchain.ursulas_accounts:
        staking_agent.commit_to_next_period(worker_address=ursula)
    testerchain.time_travel(periods=1)

    periods = 2
    status_command = ('locked-tokens',
                      '--registry-filepath', agency_local_registry.filepath,
                      '--provider', TEST_PROVIDER_URI,
                      '--network', TEMPORARY_DOMAIN,
                      '--periods', periods)
    light_parameter = [False, True]
    for light in light_parameter:
        testerchain.is_light = light
        result = click_runner.invoke(status, status_command, catch_exceptions=False)
        assert result.exit_code == 0

        current_period = staking_agent.get_current_period()
        all_locked = NU.from_nunits(staking_agent.get_global_locked_tokens(at_period=current_period))
        assert re.search(f"Locked Tokens for next {periods} periods", result.output, re.MULTILINE)
        assert re.search(f"Min: {all_locked} - Max: {all_locked}", result.output, re.MULTILINE)
