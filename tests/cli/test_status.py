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
import random

from nucypher.blockchain.eth.agents import (
    PolicyManagerAgent,
    StakingEscrowAgent,
    AdjudicatorAgent,
    NucypherTokenAgent,
    ContractAgency
)
from nucypher.blockchain.eth.constants import STAKING_ESCROW_CONTRACT_NAME
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.cli.status import status
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI

registry_filepath = '/tmp/nucypher-test-registry.json'


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    test_registry.commit(filepath=registry_filepath)


def test_nucypher_status_network(click_runner, testerchain, test_registry, agency):

    network_command = ('network',
                       '--registry-filepath', registry_filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, network_command, catch_exceptions=False)
    assert result.exit_code == 0

    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    adjudicator_agent = ContractAgency.get_agent(AdjudicatorAgent, registry=test_registry)

    # TODO: Use regex matching instead of this
    assert token_agent.contract_address in result.output
    assert staking_agent.contract_address in result.output
    assert policy_agent.contract_address in result.output
    assert adjudicator_agent.contract_address in result.output

    assert TEST_PROVIDER_URI in result.output
    assert str(staking_agent.get_current_period()) in result.output


def test_nucypher_status_stakers(click_runner, testerchain, test_registry, agency, stakers):

    # Get all stakers info
    stakers_command = ('stakers',
                       '--registry-filepath', registry_filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    # TODO: Use regex matching instead of this
    assert str(staking_agent.get_current_period()) in result.output
    for staker in stakers:
        assert staker.checksum_address in result.output

    # Get info of only one staker
    some_dude = random.choice(stakers)
    staking_address = some_dude.checksum_address
    stakers_command = ('stakers', '--staking-address', staking_address,
                       '--registry-filepath', registry_filepath,
                       '--provider', TEST_PROVIDER_URI,
                       '--poa')

    result = click_runner.invoke(status, stakers_command, catch_exceptions=False)
    assert result.exit_code == 0

    owned_tokens = NU.from_nunits(staking_agent.owned_tokens(staking_address))
    locked_tokens = NU.from_nunits(staking_agent.get_locked_tokens(staking_address))

    # TODO: Use regex matching instead of this
    assert str(staking_agent.get_current_period()) in result.output
    assert some_dude.worker_address in result.output
    assert str(round(owned_tokens, 2)) in result.output
    assert str(round(locked_tokens, 2)) in result.output


