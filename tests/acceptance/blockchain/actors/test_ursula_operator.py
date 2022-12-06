import pytest_twisted
from twisted.internet import threads

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import ContractAgency, PREApplicationAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.logging import Logger
from tests.utils.ursula import make_ursulas, start_pytest_ursula_services

logger = Logger("test-operator")


def log(message):
    logger.debug(message)
    print(message)


def test_ursula_operator_confirmation(
    ursula_test_config,
    testerchain,
    threshold_staking,
    agency,
    application_economics,
    test_registry,
):
    application_agent = ContractAgency.get_agent(
        PREApplicationAgent, registry=test_registry
    )
    (
        creator,
        staking_provider,
        operator_address,
        *everyone_else,
    ) = testerchain.client.accounts
    min_authorization = application_economics.min_authorization

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        staking_provider, min_authorization, 0, 0
    ).transact()
    testerchain.wait_for_receipt(tx)

    # make an ursula.
    blockchain_ursula = ursula_test_config.produce(
        operator_address=operator_address, rest_port=9151
    )

    # it's not confirmed
    assert blockchain_ursula.is_confirmed is False

    # it has no staking provider
    assert blockchain_ursula.get_staking_provider_address() == NULL_ADDRESS

    # now lets visit stake.nucypher.network and bond this operator
    tpower = TransactingPower(
        account=staking_provider, signer=Web3Signer(testerchain.client)
    )
    application_agent.bond_operator(
        staking_provider=staking_provider,
        operator=operator_address,
        transacting_power=tpower,
    )

    # now the worker has a staking provider
    assert blockchain_ursula.get_staking_provider_address() == staking_provider
    # but it still isn't confirmed
    assert blockchain_ursula.is_confirmed is False

    # lets confirm it.  It will probably do this automatically in real life...
    tx = blockchain_ursula.confirm_address()
    testerchain.wait_for_receipt(tx)

    assert blockchain_ursula.is_confirmed is True


@pytest_twisted.inlineCallbacks
def test_ursula_operator_confirmation_autopilot(
    mocker,
    ursula_test_config,
    testerchain,
    threshold_staking,
    agency,
    application_economics,
    test_registry,
):
    application_agent = ContractAgency.get_agent(
        PREApplicationAgent, registry=test_registry
    )
    (
        creator,
        staking_provider,
        operator,
        staking_provider2,
        operator2,
        *everyone_else,
    ) = testerchain.client.accounts
    min_authorization = application_economics.min_authorization

    commit_spy = mocker.spy(Operator, "confirm_address")
    # replacement_spy = mocker.spy(WorkTracker, '_WorkTracker__fire_replacement_commitment')

    # make an staking_providers and some stakes
    tx = threshold_staking.functions.setRoles(staking_provider2).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakes(
        staking_provider2, min_authorization, 0, 0
    ).transact()
    testerchain.wait_for_receipt(tx)

    # now lets bond this worker
    tpower = TransactingPower(
        account=staking_provider2, signer=Web3Signer(testerchain.client)
    )
    application_agent.bond_operator(
        staking_provider=staking_provider2, operator=operator2, transacting_power=tpower
    )

    # Make the Operator
    ursula = ursula_test_config.produce(operator_address=operator2, rest_port=9151)

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
        # Verify that commitment made on-chain automatically
        expected_commitments = 1
        log(f"Verifying worker made {expected_commitments} commitments so far")
        assert commit_spy.call_count == expected_commitments
        # assert replacement_spy.call_count == 0

        assert application_agent.is_operator_confirmed(operator2)

    # Behavioural Test, like a screenplay made of legos

    # Ursula confirms on startup
    d = threads.deferToThread(start)
    d.addCallback(verify_confirmed)

    yield d
