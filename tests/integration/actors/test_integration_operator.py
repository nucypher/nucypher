import random

import maya
import pytest
from twisted.logger import globalLogPublisher
from web3 import Web3

from nucypher.blockchain.eth.actors import BaseActor, Operator
from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.crypto.powers import RitualisticPower


@pytest.fixture(scope="function")
def monkeypatch_get_staking_provider_from_operator(
    real_operator_get_staking_provider_address, monkeymodule
):
    # needed to undo original monkey patch in conftest since we want the actual function called for test
    monkeymodule.setattr(
        Operator,
        "get_staking_provider_address",
        real_operator_get_staking_provider_address,
    )


@pytest.mark.usefixtures("monkeypatch_get_staking_provider_from_operator")
def test_operator_block_until_ready_failure(
    staking_providers,
    mocker,
    ursulas,
    mock_taco_application_agent,
    mock_taco_child_application_agent,
    get_random_checksum_address,
):
    ursula = ursulas[0]
    ursula_staking_provider_address = ursula.checksum_address

    # can't use 0 timeout (0 = unlimited), so need to mock maya time.
    timeout = 10
    now = maya.now()
    start_time = now
    first_iteration_time = start_time
    final_interation_time = start_time + timeout + 1

    maya_now_side_effects = [start_time, first_iteration_time, final_interation_time]

    # no actual sleeping on the job!
    mocker.patch("time.sleep", return_value=None)

    error_message = f"x Operator was not qualified after {timeout} seconds"

    # not funded and not bonded (root)
    mocker.patch.object(EthereumClient, "get_balance", return_value=0)
    mock_taco_application_agent.get_staking_provider_from_operator.return_value = (
        NULL_ADDRESS
    )

    mocker.patch("maya.now", side_effect=maya_now_side_effects)
    with pytest.raises(BaseActor.ActorError, match=error_message):
        ursula.block_until_ready(poll_rate=1, timeout=timeout)

    # funded and not bonded (root)
    mocker.patch.object(EthereumClient, "get_balance", return_value=1)
    mocker.patch("maya.now", side_effect=maya_now_side_effects)
    with pytest.raises(BaseActor.ActorError, match=error_message):
        ursula.block_until_ready(poll_rate=1, timeout=timeout)

    # funded and bonded root but not bonded for child
    mock_taco_application_agent.get_staking_provider_from_operator.return_value = (
        ursula_staking_provider_address
    )
    mock_taco_child_application_agent.staking_provider_from_operator.return_value = (
        NULL_ADDRESS
    )
    mocker.patch("maya.now", side_effect=maya_now_side_effects)
    with pytest.raises(BaseActor.ActorError, match=error_message):
        ursula.block_until_ready(poll_rate=1, timeout=timeout)

    # funded and bonded root but mismatched with child (not synced)
    mock_taco_child_application_agent.staking_provider_from_operator.return_value = (
        get_random_checksum_address()
    )
    mocker.patch("maya.now", side_effect=maya_now_side_effects)
    with pytest.raises(BaseActor.ActorError, match=error_message):
        ursula.block_until_ready(poll_rate=1, timeout=timeout)


@pytest.mark.usefixtures("monkeypatch_get_staking_provider_from_operator")
def test_operator_block_until_ready_success(
    mocker,
    ursulas,
    mock_taco_application_agent,
    mock_taco_child_application_agent,
    get_random_checksum_address,
):
    ursula = ursulas[0]

    # scenarios (iterations)
    # 1. no funding and no bonding
    # 2. funding but no bonding
    # 3. bonding but only for root not for child
    # 4. bonding but root and child are different
    # 5. bonding successful

    # funding
    final_balance_pol = Web3.to_wei(1, "ether")
    # eth funding no longer enforced
    # final_balance_eth = Web3.to_wei(2, "ether")
    mocker.patch.object(
        EthereumClient,
        "get_balance",
        side_effect=[0, 0, final_balance_pol],
    )

    # bonding
    mock_taco_application_agent.get_staking_provider_from_operator.side_effect = [
        NULL_ADDRESS,
        NULL_ADDRESS,
        ursula.checksum_address,
        ursula.checksum_address,
        ursula.checksum_address,
    ]
    mock_taco_child_application_agent.staking_provider_from_operator.side_effect = [
        NULL_ADDRESS,
        get_random_checksum_address(),
        ursula.checksum_address,
    ]

    # mock key commitment
    mocker.patch.object(
        ursula.coordinator_agent,
        "get_provider_public_key",
        return_value=bytes(ursula.public_keys(RitualisticPower)),
    )

    log_messages = []

    def log_trapper(event):
        log_messages.append(event["log_format"])

    expected_messages = [
        # iteration 1
        (
            "not funded with POL",
            "not funded with ETH (optional)",
            "not bonded to a staking provider",
        ),
        # iteration 2
        (
            f"is funded with {Web3.from_wei(final_balance_pol, 'ether')} POL",
            # eth funding only checked once since not enforced
            # f"is funded with {Web3.from_wei(final_balance_eth, 'ether')} ETH",
            "not bonded to a staking provider",
        ),
        # iteration 3
        ("not yet synced to child application",),
        # iteration 4
        ("not yet synced to child application",),
        # iteration 5
        (
            f"{ursula.operator_address} is bonded to staking provider {ursula.checksum_address}",
        ),
    ]

    def mock_time_sleep(*args, **kwargs):
        # no actual sleeping; but indication when iteration is complete
        iteration_messages = expected_messages.pop(0)
        for index, message in enumerate(iteration_messages):
            assert message in log_messages[index]
        log_messages.clear()

    mocker.patch("time.sleep", side_effect=mock_time_sleep)

    globalLogPublisher.addObserver(log_trapper)
    try:
        ursula.block_until_ready(poll_rate=1, timeout=10)
    finally:
        globalLogPublisher.removeObserver(log_trapper)


def test_operator_caching_of_signing_cohort(mocker, ursulas):
    cohort_size = 8
    cohort = list(
        sorted(ursulas[:cohort_size], key=lambda x: int(x.checksum_address, 16))
    )
    now = maya.now()

    agent = mocker.Mock(spec=SigningCoordinatorAgent)
    agent.is_cohort_active.return_value = True

    # use any ursula to determine default cache expiry
    default_cache_expiry = cohort[0]._signing_cohort_cache.ttl

    mocked_signing_cohort = mocker.Mock(spec=SigningCoordinator.SigningCohort)
    # 5 minute expiry > 60s
    mocked_signing_cohort.end_timestamp = now.add(
        minutes=default_cache_expiry * 5
    ).epoch
    agent.get_signing_cohort.return_value = mocked_signing_cohort

    for u in cohort:
        u.signing_coordinator_agent = agent

    cohort_id = 1234

    #
    # Simple caching behaviour
    #
    # call get_signing_cohort via _get_signing_cohort on each ursula in cohort
    for u in cohort:
        assert u._signing_cohort_cache[cohort_id] is None
        signing_cohort = u._get_signing_cohort(cohort_id)
        assert signing_cohort == mocked_signing_cohort
        # cache is populated
        assert u._signing_cohort_cache[cohort_id] == mocked_signing_cohort

    #
    # Cache repopulated after expiry
    #
    # pick a portion of them to clear cache (simulate cache expiry)
    ursulas_to_clear = random.sample(cohort, k=len(cohort) // 2)
    for u in ursulas_to_clear:
        u._signing_cohort_cache.remove(cohort_id)
        assert u._signing_cohort_cache[cohort_id] is None

    agent.reset_mock()
    for u in cohort:
        signing_cohort = u._get_signing_cohort(cohort_id)
        assert signing_cohort == mocked_signing_cohort
        # cache is populated
        assert u._signing_cohort_cache[cohort_id] == mocked_signing_cohort

    # ensure that get_signing_cohort was only called for ursulas that cleared cache
    assert agent.get_signing_cohort.call_count == len(ursulas_to_clear)

    # all caches populated again
    for u in cohort:
        assert u._signing_cohort_cache[cohort_id] == mocked_signing_cohort

    #
    # Test caching behaviour for soon to be expired cohort
    #
    # clear all caches
    for u in cohort:
        u._signing_cohort_cache.remove(cohort_id)
        assert u._signing_cohort_cache[cohort_id] is None

    # simulate that cohort is about to expire (before default ttl expiry)
    expiry_before_ttl_seconds = default_cache_expiry // 2
    mocked_signing_cohort.end_timestamp = now.add(
        seconds=expiry_before_ttl_seconds
    ).epoch

    agent.reset_mock()
    for u in cohort:
        signing_cohort = u._get_signing_cohort(cohort_id)
        assert signing_cohort == mocked_signing_cohort
        # cache is repopulated
        assert u._signing_cohort_cache[cohort_id] == mocked_signing_cohort

    # ensure that get_signing_cohort was called for all ursulas since cache was cleared
    assert agent.get_signing_cohort.call_count == len(cohort)

    # cache is used before expiry
    agent.reset_mock()
    for u in cohort:
        signing_cohort = u._get_signing_cohort(cohort_id)
        assert signing_cohort == mocked_signing_cohort
    # agent not called since cache is still valid
    assert agent.get_signing_cohort.call_count == 0

    agent.reset_mock()
    with mocker.patch(
        "maya.now", return_value=now.add(seconds=expiry_before_ttl_seconds + 1)
    ):
        # cohort is no longer active
        agent.is_cohort_active.return_value = False

        # cache should have expired now, so contract agent should have been called
        for u in cohort:
            with pytest.raises(Operator.UnauthorizedRequest, match="is not active"):
                _ = u._get_signing_cohort(cohort_id)

        # cache attempted to be repopulated by all nodes but cohort is realized to be inactive
        #  after checking on-chain
        assert agent.is_cohort_active.call_count == len(cohort)
        assert agent.get_signing_cohort.call_count == 0

    # very unlikely case where cohort was active but expired after we check on-chain
    #  but before we cache it
    agent.reset_mock()
    with mocker.patch(
        "maya.now", return_value=now.add(seconds=expiry_before_ttl_seconds + 1)
    ):
        # cohort is active
        agent.is_cohort_active.return_value = True

        # cache should have expired now, so contract agent should have been called
        for u in cohort:
            with pytest.raises(Operator.UnauthorizedRequest, match="is not active"):
                _ = u._get_signing_cohort(cohort_id)

        # cache attempted to be repopulated by all nodes but cohort is realized to be inactive
        #  after checking on-chain
        assert agent.is_cohort_active.call_count == len(cohort)
        assert agent.get_signing_cohort.call_count == len(
            cohort
        )  # actually called this time
