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

from nucypher.blockchain.eth.actors import Staker, Bidder
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    WorkLockAgent
)
from nucypher.characters.lawful import Ursula
from nucypher.cli.commands.worklock import worklock
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    MOCK_IP_ADDRESS,
    select_test_port
)


def test_status(click_runner, testerchain, agency_local_registry):
    command = ('status',
               '--registry-filepath', agency_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_bid(click_runner, testerchain, agency_local_registry, token_economics):

    # Wait until biding window starts
    testerchain.time_travel(seconds=90)

    bid_value = to_wei(4, 'ether')
    base_command = ('bid',
                    '--value', bid_value,
                    '--registry-filepath', agency_local_registry.filepath,
                    '--provider', TEST_PROVIDER_URI,
                    '--poa',
                    '--debug',
                    '--force')

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)
    total_bids = 0
    # Multiple bidders
    for bidder in testerchain.unassigned_accounts[:3]:
        pre_bid_balance = testerchain.client.get_balance(bidder)

        command = (*base_command, '--bidder-address', bidder)
        result = click_runner.invoke(worklock, command, catch_exceptions=False)
        assert result.exit_code == 0

        post_bid_balance = testerchain.client.get_balance(bidder)
        difference = pre_bid_balance - post_bid_balance
        assert difference >= bid_value

        total_bids += bid_value
        assert testerchain.client.get_balance(worklock_agent.contract_address) == total_bids


def test_cancel_bid(click_runner, testerchain, agency_local_registry, token_economics):
    bidder = testerchain.unassigned_accounts[0]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    command = ('cancel-bid',
               '--bidder-address', bidder,
               '--registry-filepath', agency_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--force',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
    assert not agent.get_deposited_eth(bidder)    # No more bid


def test_claim(click_runner, testerchain, agency_local_registry, token_economics):

    # Wait until the end of the bidding period
    testerchain.time_travel(token_economics.bidding_duration+2)

    bidder = testerchain.unassigned_accounts[1]
    command = ('claim',
               '--bidder-address', bidder,
               '--registry-filepath', agency_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_remaining_work(click_runner, testerchain, agency_local_registry, token_economics):
    bidder = testerchain.unassigned_accounts[1]

    # Ensure there is remaining work one layer below
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)
    remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert remaining_work > 0

    command = ('remaining-work',
               '--bidder-address', bidder,
               '--registry-filepath', agency_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # Ensure were displaying the bidder address and remaining work in the output
    assert bidder in result.output
    assert str(remaining_work) in result.output


def test_refund(click_runner, testerchain, agency_local_registry, token_economics):

    bidder = testerchain.unassigned_accounts[1]
    worker_address = testerchain.unassigned_accounts[-1]

    #
    # WorkLock Staker-Worker
    #

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    # Bidder is now STAKER. Bond a worker.
    staker = Staker(is_me=True, checksum_address=bidder, registry=agency_local_registry)
    receipt = staker.set_worker(worker_address=worker_address)
    assert receipt['status'] == 1

    worker = Ursula(is_me=True,
                    registry=agency_local_registry,
                    checksum_address=bidder,
                    worker_address=worker_address,
                    rest_host=MOCK_IP_ADDRESS,
                    rest_port=select_test_port())

    # Ensure there is work to do
    remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert remaining_work > 0

    # Do some work
    for i in range(3):
        receipt = worker.confirm_activity()
        assert receipt['status'] == 1
        testerchain.time_travel(periods=1)

    command = ('refund',
               '--bidder-address', bidder,
               '--registry-filepath', agency_local_registry.filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug',
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # Less work to do...
    new_remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert new_remaining_work < remaining_work


def test_participant_status(click_runner, testerchain, agency_local_registry, token_economics):
    bidder = Bidder(checksum_address=testerchain.unassigned_accounts[1], registry=agency_local_registry)

    command = ('status',
               '--registry-filepath', agency_local_registry.filepath,
               '--bidder-address', bidder.checksum_address,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    # Bidder-specific data is displayed
    assert bidder.checksum_address in result.output
    assert str(bidder.remaining_work) in result.output
    assert str(bidder.available_refund) in result.output

    # Worklock economics are displayed
    assert str(token_economics.worklock_boosting_refund_rate) in result.output
    assert str(token_economics.worklock_supply) in result.output


@pytest.mark.skip()
def test_burn_unclaimed_tokens(click_runner, testerchain, agency_local_registry):
    # Wait until biding window starts
    testerchain.time_travel(periods=10)

    philanthropist = testerchain.unassigned_accounts[4]
    command = ('burn-unclaimed-tokens',
               '--registry-filepath', agency_local_registry,
               '--checksum-address', philanthropist,
               '--provider', TEST_PROVIDER_URI,
               '--poa',
               '--debug')

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    # There are unclaimed tokens
    assert worklock_agent.get_unclaimed_tokens() > 0
    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
    # No more unclaimed tokens
    assert worklock_agent.get_unclaimed_tokens() == 0
