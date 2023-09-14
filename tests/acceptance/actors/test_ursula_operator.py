import os

import pytest
import pytest_twisted
from hexbytes import HexBytes
from twisted.internet import threads
from twisted.internet.task import Clock
from web3.middleware.simulate_unmined_transaction import (
    INVOCATIONS_BEFORE_RESULT,
    unmined_receipt_simulator_middleware,
)

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.trackers.pre import WorkTracker, WorkTrackerBase
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import Logger
from tests.utils.ursula import select_test_port, start_pytest_ursula_services

logger = Logger("test-operator")

def log(message):
    logger.debug(message)
    print(message)


@pytest.mark.usefixtures("test_registry_source_manager")
def test_ursula_operator_confirmation(
    ursula_test_config,
    testerchain,
    threshold_staking,
    taco_application_agent,
    test_registry,
    deployer_account,
):
    staking_provider = testerchain.stake_provider_account(0)
    operator_address = testerchain.ursula_account(0)
    min_authorization = taco_application_agent.get_min_authorization()

    # make an staking_providers and some stakes
    threshold_staking.setRoles(staking_provider, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider,
        0,
        min_authorization,
        sender=deployer_account,
    )

    # not staking provider just yet
    assert (
        taco_application_agent.get_staking_provider_from_operator(operator_address)
        == NULL_ADDRESS
    )
    assert taco_application_agent.is_operator_confirmed(operator_address) is False

    # bond this operator
    tpower = TransactingPower(
        account=staking_provider, signer=Web3Signer(testerchain.client)
    )
    taco_application_agent.bond_operator(
        staking_provider=staking_provider,
        operator=operator_address,
        transacting_power=tpower,
    )

    # make an ursula.
    ursula = ursula_test_config.produce(
        operator_address=operator_address, rest_port=select_test_port()
    )

    # now the worker has a staking provider
    assert ursula.get_staking_provider_address() == staking_provider
    # confirmed on Ursula creation
    assert ursula.is_confirmed is True


@pytest_twisted.inlineCallbacks
def test_ursula_operator_confirmation_autopilot(
    mocker,
    ursula_test_config,
    testerchain,
    threshold_staking,
    taco_application_agent,
    test_registry,
    deployer_account,
):
    staking_provider2 = testerchain.stake_provider_account(1)
    operator2 = testerchain.ursula_account(1)
    min_authorization = taco_application_agent.get_min_authorization()

    confirmation_spy = mocker.spy(Operator, "set_provider_public_key")
    # TODO: WorkerTracker may no longer be needed
    replacement_confirmation_spy = mocker.spy(
        WorkTrackerBase, "_WorkTrackerBase__fire_replacement_commitment"
    )

    # make an staking_providers and some stakes
    threshold_staking.setRoles(staking_provider2, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider2, 0, min_authorization, sender=deployer_account
    )

    # now lets bond this worker
    tpower = TransactingPower(
        account=staking_provider2, signer=Web3Signer(testerchain.client)
    )
    taco_application_agent.bond_operator(
        staking_provider=staking_provider2, operator=operator2, transacting_power=tpower
    )

    # Make the Operator
    ursula = ursula_test_config.produce(
        operator_address=operator2, rest_port=select_test_port()
    )

    ursula.run(
        preflight=False,
        discovery=False,
        start_reactor=False,
        worker=True,
        eager=True,
        block_until_ready=True,
    )  # "start" services

    def start():
        log("Starting Operator for auto confirm address simulation")
        start_pytest_ursula_services(ursula=ursula)

    def verify_confirmed(_):
        # Verify that confirmation made on-chain automatically
        expected_confirmations = 1
        log(f"Verifying worker made {expected_confirmations} commitment so far")
        assert confirmation_spy.call_count == expected_confirmations
        assert replacement_confirmation_spy.call_count == 0  # no replacement txs needed
        assert taco_application_agent.is_operator_confirmed(operator2) is True

    # Behavioural Test, like a screenplay made of legos

    # Ursula confirms on startup
    d = threads.deferToThread(start)
    d.addCallback(verify_confirmed)

    yield d


@pytest_twisted.inlineCallbacks
def test_work_tracker(
    mocker,
    ursula_test_config,
    testerchain,
    threshold_staking,
    taco_application_agent,
    test_registry,
    deployer_account,
):
    staking_provider3 = testerchain.stake_provider_account(2)
    operator3 = testerchain.ursula_account(2)
    min_authorization = taco_application_agent.get_min_authorization()

    # Mock confirm_operator transaction
    def mock_confirm_operator_tx_hash(*args, **kwargs):
        # rando txHash
        return HexBytes(os.urandom(32))

    # Mock return that operator is not confirmed
    mocker.patch.object(
        taco_application_agent, "is_operator_confirmed", return_value=False
    )
    mocker.patch.object(
        taco_application_agent,
        "confirm_operator_address",
        side_effect=mock_confirm_operator_tx_hash,
    )

    # deterministic wait for replacement transaction to be mined
    mocker.patch.object(
        WorkTrackerBase,
        "max_confirmation_time",
        return_value=WorkTracker.INTERVAL_FLOOR,
    )

    # Spies
    confirmation_spy = mocker.spy(Operator, "confirm_address")
    replacement_confirmation_spy = mocker.spy(
        WorkTrackerBase, "_WorkTrackerBase__fire_replacement_commitment"
    )

    # Control time
    clock = Clock()
    WorkTrackerBase.CLOCK = clock

    # make an staking_providers and some stakes
    threshold_staking.setRoles(staking_provider3, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        staking_provider3, 0, min_authorization, sender=deployer_account
    )

    # now lets bond this worker
    tpower = TransactingPower(
        account=staking_provider3, signer=Web3Signer(testerchain.client)
    )
    taco_application_agent.bond_operator(
        staking_provider=staking_provider3, operator=operator3, transacting_power=tpower
    )

    # Make the Operator
    ursula = ursula_test_config.produce(
        operator_address=operator3, rest_port=select_test_port()
    )

    def start(_):
        log("Starting Worker services")
        start_pytest_ursula_services(ursula=ursula)

    def advance_clock_interval(_):
        # note: for the test replacement tx confirmation time is <= next run
        log("Advance clock interval to next run")
        next_tracker_run = ursula.work_tracker._tracking_task.interval + 1
        # replacement tx time uses block number so advance chain as well
        testerchain.time_travel(next_tracker_run)
        clock.advance(next_tracker_run)

    def simulate_unmined_transactions():
        log("Starting unmined transaction simulation")
        testerchain.client.add_middleware(unmined_receipt_simulator_middleware)

    def check_pending_confirmation(_):
        log("Worker is currently tracking an unmined transaction")
        assert len(ursula.work_tracker.pending) == 1  # only ever tracks one tx

    def verify_confirm_operator_calls(_):
        log("Verifying worker calls to confirm_operator")
        # one less replacement tx than total count (initial + replacements)
        assert (
            confirmation_spy.call_count == replacement_confirmation_spy.call_count + 1
        )

    def verify_replacement_confirm_operator_call(_):
        log("Verifying worker has issued replaced confirmation transaction")
        # one less replacement tx than total count
        assert replacement_confirmation_spy.call_count == (
            confirmation_spy.call_count - 1
        )

    def verify_confirmed(_):
        # Verify that commitment made on-chain automatically
        log("Verifying operator is confirmed")
        assert taco_application_agent.is_operator_confirmed(operator3) is True

    def verify_not_yet_confirmed(_):
        # Verify that commitment made on-chain automatically
        log("Verifying operator is not confirmed")
        assert taco_application_agent.is_operator_confirmed(operator3) is False

    # Behavioural Test, like a screenplay made of legos
    # Simulate unmined transactions
    d = threads.deferToThread(simulate_unmined_transactions)

    # Run ursula and start services
    ursula.run(
        preflight=False,
        discovery=False,
        start_reactor=False,
        worker=True,
        eager=True,
        block_until_ready=True,
    )
    d.addCallback(start)

    # there is an attempt to confirm operator on Ursula start
    d.addCallback(verify_confirm_operator_calls)

    # Ensure not yet confirmed; technically it is, but we mock that it isn't
    d.addCallback(verify_not_yet_confirmed)

    # Ursula's confirm_operator transaction remains unmined and gets stuck
    for i in range(INVOCATIONS_BEFORE_RESULT - 1):
        d.addCallback(advance_clock_interval)
        d.addCallback(verify_confirm_operator_calls)

        d.addCallback(verify_replacement_confirm_operator_call)

        d.addCallback(verify_not_yet_confirmed)
        d.addCallback(check_pending_confirmation)

    # Ursula recovers from this situation
    d.addCallback(advance_clock_interval)

    d.addCallback(verify_confirm_operator_calls)
    d.addCallback(verify_replacement_confirm_operator_call)

    yield d

    # allow operator to be considered confirmed
    mocker.patch.object(
        taco_application_agent, "is_operator_confirmed", return_value=True
    )
    d.addCallback(verify_confirmed)

    yield d

    # initial call + 5 replacements until is_operator_confirmed is mocked to True
    # (no more afterwards)
    assert confirmation_spy.call_count == 6
    assert replacement_confirmation_spy.call_count == 5

    # now that operator is confirmed there should be no more confirm_operator calls
    for i in range(3):
        d.addCallback(advance_clock_interval)

    yield d
    assert confirmation_spy.call_count == 6  # no change in number
    assert replacement_confirmation_spy.call_count == 5
