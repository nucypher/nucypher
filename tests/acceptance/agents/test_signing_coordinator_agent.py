import pytest
import pytest_twisted
from eth_abi import encode
from twisted.internet import reactor
from twisted.internet.task import deferLater
from web3 import Web3

from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.crypto.powers import TransactingPower


@pytest.fixture(scope="module")
def agent(signing_coordinator_agent) -> SigningCoordinatorAgent:
    return signing_coordinator_agent


@pytest.mark.usefixtures("ursulas")
@pytest.fixture(scope="module")
def cohort_providers(staking_providers):
    # "ursulas" fixture is needed to set provider public key
    deployer, cohort_provider_1, cohort_provider_2, *everybody_else = staking_providers
    cohort_providers = [cohort_provider_1, cohort_provider_2]
    cohort_providers.sort()  # providers must be sorted
    return cohort_providers


@pytest.fixture(scope="module")
def cohort_operators(cohort_providers, taco_application_agent):
    ursulas_for_cohort = []
    for provider in cohort_providers:
        operator = taco_application_agent.get_operator_from_staking_provider(provider)
        ursulas_for_cohort.append(operator)

    return ursulas_for_cohort


@pytest.fixture(scope="module")
def transacting_powers(accounts, cohort_operators):
    return [
        TransactingPower(account=ursula, signer=accounts.get_account_signer(ursula))
        for ursula in cohort_operators
    ]


@pytest.fixture(scope="module")
def authority(get_random_checksum_address):
    return get_random_checksum_address()


# TODO figure out why I can't do this in conftest.py
@pytest.fixture(scope="module")
def ritual_initiator(initiator, signing_coordinator, deployer_account):
    signing_coordinator.grantRole(
        signing_coordinator.INITIATOR_ROLE(),
        initiator.transacting_power.account,
        sender=deployer_account,
    )
    return initiator


@pytest.mark.usefixtures("ursulas")
def test_initiate_signing_cohort(
    accounts,
    agent,
    cohort_providers,
    authority,
    transacting_powers,
    testerchain,
    ritual_initiator,
):
    number_of_cohorts = agent.number_of_cohorts()
    assert number_of_cohorts == 0

    duration = 60 * 60 * 24

    receipt = agent.initiate_signing_cohort(
        authority=authority,
        providers=cohort_providers,
        threshold=len(cohort_providers) // 2 + 1,
        duration=duration,
        transacting_power=ritual_initiator.transacting_power,
    )
    assert receipt["status"] == 1
    initiate_event = agent.contract.events.InitiateSigningCohort().process_receipt(
        receipt
    )
    assert initiate_event[0]["args"]["authority"] == authority
    assert initiate_event[0]["args"]["participants"] == cohort_providers

    number_of_cohorts = agent.number_of_cohorts()
    assert number_of_cohorts == 1
    cohort_id = number_of_cohorts - 1

    signing_cohort = agent.get_signing_cohort(cohort_id)
    assert signing_cohort.authority == authority
    assert [p.provider for p in signing_cohort.signers] == cohort_providers

    assert (
        agent.get_signing_cohort_status(cohort_id=cohort_id)
        == SigningCoordinator.RitualStatus.AWAITING_SIGNATURES
    )


@pytest_twisted.inlineCallbacks
@pytest.mark.usefixtures()
def test_post_signature(
    accounts,
    agent,
    transacting_powers,
    authority,
    cohort_providers,
    cohort_operators,
    testerchain,
    clock,
    mock_async_hooks,
    nucypher_dependency,
):
    cohort_id = agent.number_of_cohorts() - 1

    assert (
        agent.get_signing_cohort_status(cohort_id=cohort_id)
        == SigningCoordinator.RitualStatus.AWAITING_SIGNATURES
    )

    txs = []
    signatures = []
    for transacting_power in transacting_powers:
        data = encode(["uint32", "address"], [cohort_id, authority])
        digest = Web3.keccak(data)
        signature = transacting_power.sign_message(digest, standardize=False)
        async_tx = agent.post_signature(
            cohort_id=cohort_id,
            signature=signature,
            transacting_power=transacting_power,
            async_tx_hooks=mock_async_hooks,
        )
        signatures.append(signature)
        txs.append(async_tx)

    testerchain.tx_machine.start()
    while not all([tx.final for tx in txs]):
        yield clock.advance(testerchain.tx_machine._task.interval)
    testerchain.tx_machine.stop()

    for i, async_tx in enumerate(txs):
        post_signature_events = (
            agent.contract.events.SigningCohortSignaturePosted().process_receipt(
                async_tx.receipt
            )
        )
        event = post_signature_events[0]
        assert event["args"]["cohortId"] == cohort_id
        assert event["args"]["signature"] == signatures[i]

    # ensure relevant hooks are called (once for each tx) OR not called (failure ones)
    yield deferLater(reactor, 0.2, lambda: None)
    assert mock_async_hooks.on_broadcast.call_count == len(txs)
    assert mock_async_hooks.on_finalized.call_count == len(txs)
    for async_tx in txs:
        assert async_tx.successful is True

    # failure hooks not called
    assert mock_async_hooks.on_broadcast_failure.call_count == 0
    assert mock_async_hooks.on_fault.call_count == 0
    assert mock_async_hooks.on_insufficient_funds.call_count == 0

    assert (
        agent.get_signing_cohort_status(cohort_id=cohort_id)
        == SigningCoordinator.RitualStatus.ACTIVE
    )
    assert agent.is_cohort_active(cohort_id=cohort_id)

    signing_cohort = agent.get_signing_cohort(cohort_id)
    for i, signer in enumerate(signing_cohort.signers):
        assert signer.provider == cohort_providers[i]
        assert signer.operator == cohort_operators[i]
        assert signer.signature == signatures[i]

    # check deployed multisig
    deployed_multisig = nucypher_dependency.ThresholdSigningMultisig.at(
        signing_cohort.multisig
    )
    assert deployed_multisig.getSigners() == cohort_operators
    assert deployed_multisig.threshold() == len(cohort_operators) // 2 + 1
    assert deployed_multisig.owner() == authority
