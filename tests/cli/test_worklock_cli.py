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

from nucypher.blockchain.eth.agents import (
    StakingEscrowAgent,
    ContractAgency
)
from nucypher.blockchain.eth.deployers import WorkLockDeployer
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.cli.status import status
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import TEST_PROVIDER_URI, INSECURE_DEVELOPMENT_PASSWORD

registry_filepath = '/tmp/nucypher-test-registry.json'
# staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
DEPOSIT_RATE = 100


@pytest.fixture(scope="module", autouse=True)
def funded_worklock(testerchain, agency, test_registry, token_economics):

    # Unlock
    transacting_power = TransactingPower(account=testerchain.etherbase_account,
                                         password=INSECURE_DEVELOPMENT_PASSWORD)
    transacting_power.activate()

    # Deploy
    deployer = WorkLockDeployer(registry=test_registry,
                                deployer_address=testerchain.etherbase_account,
                                economics=token_economics)
    _deployment_receipts = deployer.deploy()

    # Fund.
    worklock_supply = 2 * token_economics.maximum_allowed_locked - 1
    receipt = deployer.fund(sender_address=testerchain.etherbase_account, value=worklock_supply)
    assert receipt['status'] == 1

    return deployer


@pytest.fixture(scope='module', autouse=True)
def temp_registry(testerchain, test_registry, agency):
    # Disable registry fetching, use the mock one instead
    InMemoryContractRegistry.download_latest_publication = lambda: registry_filepath
    test_registry.commit(filepath=registry_filepath)


def test_status(click_runner, testerchain, test_registry, agency):
    command = ('status',
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa')

    result = click_runner.invoke(status, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_bid(click_runner, testerchain, test_registry, agency):
    bidder = testerchain.unassigned_accounts[-1]
    command = ('bid',
               'bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa')

    result = click_runner.invoke(status, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_remaining_work(click_runner, testerchain, agency):
    bidder = testerchain.unassigned_accounts[-1]

    command = ('remaining-work',
               'bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa')

    result = click_runner.invoke(status, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_claim(click_runner, testerchain, agency):
    bidder = testerchain.unassigned_accounts[-1]

    command = ('claim',
               'bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa')

    result = click_runner.invoke(status, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_refund(click_runner, testerchain, agency):
    bidder = testerchain.unassigned_accounts[-1]

    command = ('refund',
               'bidder-address', bidder,
               '--registry-filepath', registry_filepath,
               '--provider', TEST_PROVIDER_URI,
               '--poa')

    result = click_runner.invoke(status, command, catch_exceptions=False)
    assert result.exit_code == 0
