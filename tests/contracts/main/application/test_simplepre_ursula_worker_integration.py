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
import pytest_twisted
from twisted.internet import threads
from twisted.internet.task import Clock

from eth_tester.exceptions import TransactionFailed
from web3.middleware.simulate_unmined_transaction import unmined_receipt_simulator_middleware

from nucypher.utilities.logging import Logger
logger = Logger("test-worker")
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import WorkTrackerBaseClass as WorkTracker
from nucypher.blockchain.eth.actors import ThresholdWorker as Worker
from nucypher.config.constants import USER_LOG_DIR

from eth_utils import to_checksum_address
from constant_sorrow.constants import MOCK_DB
from tests.utils.ursula import start_pytest_ursula_services


CONFIRMATION_SLOT = 1
MIN_WORKER_SECONDS = 24 * 60 * 60


def log(message):
    logger.debug(message)
    print(message)


def test_ursula_contract_interaction_methods(ursula_decentralized_test_config, testerchain, threshold_staking, pre_application,
                                             application_economics, deploy_contract, test_registry_source_manager):
    creator, staking_provider, operator_address, *everyone_else = testerchain.client.accounts
    min_authorization = application_economics.min_authorization

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    # make an ursula.
    blockchain_ursula = ursula_decentralized_test_config.produce(
        worker_address=worker_address,
        db_filepath=MOCK_DB,
        rest_port=9151)

    # it's not confirmed
    assert blockchain_ursula.is_confirmed is False

    # it has no staking provider
    assert blockchain_ursula.get_staking_provider_address() == NULL_ADDRESS

    # now lets visit stake.nucypher.network and bond this worker
    tx = pre_application.functions.bondOperator(staking_provider, worker_address).transact({'from': staking_provider})
    testerchain.wait_for_receipt(tx)

    # now the worker has a staking provider
    assert blockchain_ursula.get_staking_provider_address() == staking_provider
    # but it still isn't confirmed
    assert blockchain_ursula.is_confirmed is False

    # lets confirm it.  It will probably do this automatically in real life...
    tx = blockchain_ursula.confirm_operator_address()
    testerchain.wait_for_receipt(tx)

    assert blockchain_ursula.is_confirmed is True


@pytest_twisted.inlineCallbacks
def test_integration_of_ursula_contract_interaction(mocker, ursula_decentralized_test_config, testerchain, threshold_staking, pre_application, token_economics, deploy_contract):

    creator, staking_provider, operator, staking_provider2, operator2, *everyone_else = testerchain.client.accounts
    min_authorization = token_economics.minimum_allowed_locked

    commit_spy = mocker.spy(Worker, 'confirm_operator_address')
    # replacement_spy = mocker.spy(WorkTracker, '_WorkTracker__fire_replacement_commitment')

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(staking_provider2, min_authorization, 0, 0).transact()
    testerchain.wait_for_receipt(tx)

    # now lets bond this worker
    tx = pre_application.functions.bondOperator(staking_provider2, operator2).transact({'from': staking_provider2})
    testerchain.wait_for_receipt(tx)

    # Make the Worker
    ursula = ursula_decentralized_test_config.produce(
        worker_address=operator2,
        db_filepath=MOCK_DB,
        rest_port=9151)

    ursula.run(preflight=False,
               discovery=False,
               start_reactor=False,
               worker=True,
               eager=True,
               block_until_ready=True)  # "start" services

    def start():
        log("Starting Worker for auto confirm address simulation")
        start_pytest_ursula_services(ursula=ursula)


    def verify_confirmed(_):
        # Verify that periods were committed on-chain automatically
        expected_commitments = 1
        log(f'Verifying worker made {expected_commitments} commitments so far')
        assert commit_spy.call_count == expected_commitments
        # assert replacement_spy.call_count == 0

        assert pre_application.functions.isOperatorConfirmed(operator2).call()

    # Behavioural Test, like a screenplay made of legos

    # Ursula confirms on startup
    d = threads.deferToThread(start)
    d.addCallback(verify_confirmed)

    yield d
