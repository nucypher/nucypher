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
from eth_utils import to_wei

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    WorkLockAgent
)
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, IndividualAllocationRegistry
from nucypher.characters.lawful import Ursula
from nucypher.cli.worklock import worklock
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    MOCK_IP_ADDRESS,
    select_test_port
)

registry_filepath = '/tmp/nucypher-test-registry.json'


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    test_registry.commit(filepath=registry_filepath, overwrite=True)


def test_status(click_runner, testerchain, test_registry, agency):
    command = ('status',
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_bid(click_runner, testerchain, test_registry, agency, token_economics):

    # Wait until biding window starts
    testerchain.time_travel(seconds=90)

    bidder = testerchain.unassigned_accounts[-1]
    bid_value = to_wei(4, 'ether')

    command = ('bid',
               '--bidder-address', bidder,
               '--value', bid_value,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug',
               '--force')

    pre_bid_balance = testerchain.client.get_balance(bidder)
    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    post_bid_balance = testerchain.client.get_balance(bidder)
    difference = pre_bid_balance - post_bid_balance
    assert difference >= bid_value

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert testerchain.client.get_balance(worklock_agent.contract_address) == bid_value


def test_claim(click_runner, testerchain, agency, token_economics):

    # Wait until the end of the bidding period
    testerchain.time_travel(token_economics.bidding_duration+2)

    bidder = testerchain.unassigned_accounts[-1]
    command = ('claim',
               '--bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_remaining_work(click_runner, testerchain, test_registry, agency, token_economics):
    bidder = testerchain.unassigned_accounts[-1]

    command = ('remaining-work',
               '--bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
    assert bidder in result.output


def test_refund(click_runner, testerchain, agency, test_registry, token_economics):

    bidder = testerchain.unassigned_accounts[-1]

    #
    # WorkLock Staker-Worker
    #

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    allocation_address = worklock_agent.get_allocation_from_bidder(bidder_address=bidder)
    individual_allocation = IndividualAllocationRegistry(beneficiary_address=bidder,
                                                         contract_address=allocation_address)

    # No stake initialization is needed, since claiming worklock tokens.
    staker = Staker(is_me=True,
                    checksum_address=bidder,
                    registry=test_registry,
                    individual_allocation=individual_allocation)
    staker.set_worker(worker_address=bidder)

    worker = Ursula(is_me=True,
                    registry=test_registry,
                    checksum_address=bidder,
                    worker_address=bidder,
                    rest_host=MOCK_IP_ADDRESS,
                    rest_port=select_test_port())

    for i in range(10):
        worker.confirm_activity()
        testerchain.time_travel(periods=1)

    command = ('refund',
               '--bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug',
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_participant_status(click_runner, testerchain, test_registry, agency):
    bidder = testerchain.unassigned_accounts[-1]

    command = ('status',
               '--registry-filepath', registry_filepath,
               '--bidder-address', bidder,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_burn_unclaimed_tokens(click_runner, testerchain, test_registry, agency):
    philanthropist = testerchain.unassigned_accounts[-1]

    # Ensure there are unclaimed tokens to burn
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert worklock_agent.get_unclaimed_tokens()

    command = ('burn-unclaimed-tokens',
               '--registry-filepath', registry_filepath,
               '--checksum-address', philanthropist,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # No more unclaimed tokens
    assert worklock_agent.get_unclaimed_tokens() == 0
