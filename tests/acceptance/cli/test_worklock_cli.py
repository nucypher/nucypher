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
import tempfile

import pytest
from eth_utils import to_wei
from web3 import Web3

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.actors import Bidder, Staker
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    WorkLockAgent
)
from nucypher.blockchain.eth.token import NU
from nucypher.characters.lawful import Ursula
from nucypher.cli.commands.worklock import worklock
from tests.constants import (INSECURE_DEVELOPMENT_PASSWORD, MOCK_IP_ADDRESS, TEST_PROVIDER_URI, MOCK_PROVIDER_URI)
from tests.utils.ursula import select_test_port
from nucypher.config.constants import TEMPORARY_DOMAIN


@pytest.fixture(scope='module')
def bids(testerchain):
    bids_distribution = dict()

    min_bid_eth_value = 1
    max_bid_eth_value = 10

    whale = testerchain.client.accounts[0]
    bids_distribution[whale] = 50_000
    for bidder in testerchain.client.accounts[1:12]:
        bids_distribution[bidder] = random.randrange(min_bid_eth_value, max_bid_eth_value)

    return bids_distribution


def test_status(click_runner, testerchain, agency_local_registry, token_economics):
    command = ('status',
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)

    assert result.exit_code == 0
    assert str(NU.from_nunits(token_economics.worklock_supply)) in result.output
    assert str(Web3.fromWei(token_economics.worklock_min_allowed_bid, 'ether')) in result.output


def test_bid(click_runner, testerchain, agency_local_registry, token_economics, bids):

    # Wait until biding window starts
    testerchain.time_travel(seconds=90)

    base_command = ('escrow',
                    '--registry-filepath', str(agency_local_registry.filepath.absolute()),
                    '--provider', TEST_PROVIDER_URI,
                    '--signer', TEST_PROVIDER_URI,
                    '--network', TEMPORARY_DOMAIN,
                    '--force')

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)
    total_bids = 0
    # Multiple bidders
    for bidder, bid_eth_value in bids.items():
        pre_bid_balance = testerchain.client.get_balance(bidder)
        assert pre_bid_balance > to_wei(bid_eth_value, 'ether')

        command = (*base_command, '--participant-address', bidder, '--value', bid_eth_value)
        user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
        result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
        assert result.exit_code == 0

        post_bid_balance = testerchain.client.get_balance(bidder)
        difference = pre_bid_balance - post_bid_balance
        assert difference >= to_wei(bid_eth_value, 'ether')

        total_bids += to_wei(bid_eth_value, 'ether')
        assert testerchain.client.get_balance(worklock_agent.contract_address) == total_bids


def test_cancel_bid(click_runner, testerchain, agency_local_registry, token_economics, bids):

    bidders = list(bids.keys())

    bidder = bidders[-1]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    command = ('cancel-escrow',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert not agent.get_deposited_eth(bidder)    # No more bid

    # Wait until the end of the bidding period
    testerchain.time_travel(seconds=token_economics.bidding_duration + 2)

    bidder = bidders[-2]
    command = ('cancel-escrow',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert not agent.get_deposited_eth(bidder)    # No more bid


def test_enable_claiming(click_runner, testerchain, agency_local_registry, token_economics):

    # Wait until the end of the cancellation period
    testerchain.time_travel(seconds=token_economics.cancellation_window_duration+2)

    bidder = testerchain.client.accounts[0]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)
    assert not agent.is_claiming_available()
    assert not agent.bidders_checked()

    command = ('enable-claiming',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--force',
               '--network', TEMPORARY_DOMAIN,
               '--gas-limit', 100000)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert agent.is_claiming_available()
    assert agent.bidders_checked()


def test_claim(click_runner, testerchain, agency_local_registry, token_economics):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    bidder = testerchain.client.accounts[2]
    command = ('claim',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    whale = testerchain.client.accounts[0]
    assert agent.get_available_compensation(checksum_address=whale) > 0
    command = ('claim',
               '--participant-address', whale,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    assert agent.get_available_compensation(checksum_address=whale) == 0

    # TODO: Check successful new stake in StakingEscrow


def test_remaining_work(click_runner, testerchain, agency_local_registry, token_economics):
    bidder = testerchain.client.accounts[2]

    # Ensure there is remaining work one layer below
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)
    remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert remaining_work > 0

    command = ('remaining-work',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # Ensure were displaying the bidder address and remaining work in the output
    assert bidder in result.output
    assert str(remaining_work) in result.output


def test_refund(click_runner, testerchain, agency_local_registry, token_economics):

    bidder = testerchain.client.accounts[2]
    worker_address = testerchain.unassigned_accounts[-1]

    #
    # WorkLock Staker-Worker
    #

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=agency_local_registry)

    # Bidder is now STAKER. Bond a worker.
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))
    staker = Staker(transacting_power=tpower,
                    domain=TEMPORARY_DOMAIN,
                    registry=agency_local_registry)
    receipt = staker.bond_worker(worker_address=worker_address)
    assert receipt['status'] == 1

    worker = Ursula(is_me=True,
                    domain=TEMPORARY_DOMAIN,
                    provider_uri=MOCK_PROVIDER_URI,
                    registry=agency_local_registry,
                    checksum_address=bidder,
                    signer=Web3Signer(testerchain.client),
                    worker_address=worker_address,
                    rest_host=MOCK_IP_ADDRESS,
                    rest_port=select_test_port(),
                    db_filepath=tempfile.mkdtemp())

    # Ensure there is work to do
    remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert remaining_work > 0

    # Do some work
    testerchain.time_travel(periods=1)
    for i in range(3):
        txhash = worker.commit_to_next_period()
        testerchain.wait_for_receipt(txhash)
        assert receipt['status'] == 1
        testerchain.time_travel(periods=1)

    command = ('refund',
               '--participant-address', bidder,
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' + 'Y\n'
    result = click_runner.invoke(worklock, command, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Less work to do...
    new_remaining_work = worklock_agent.get_remaining_work(checksum_address=bidder)
    assert new_remaining_work < remaining_work


def test_participant_status(click_runner, testerchain, agency_local_registry, token_economics):

    tpower = TransactingPower(account=testerchain.client.accounts[2],
                              signer=Web3Signer(testerchain.client))
    bidder = Bidder(transacting_power=tpower,
                    domain=TEMPORARY_DOMAIN,
                    registry=agency_local_registry)

    command = ('status',
               '--registry-filepath', str(agency_local_registry.filepath.absolute()),
               '--participant-address', bidder.checksum_address,
               '--provider', TEST_PROVIDER_URI,
               '--signer', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # Bidder-specific data is displayed
    assert bidder.checksum_address in result.output
    assert str(bidder.remaining_work) in result.output
    assert str(bidder.available_refund) in result.output

    # Worklock economics are displayed
    assert str(token_economics.worklock_boosting_refund_rate) in result.output
    assert str(NU.from_nunits(token_economics.worklock_supply)) in result.output
