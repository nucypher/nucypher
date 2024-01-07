import maya
import pytest
from twisted.logger import globalLogPublisher
from web3 import Web3

from nucypher.blockchain.eth.actors import BaseActor, Operator
from nucypher.blockchain.eth.clients import EthereumClient
from nucypher.blockchain.eth.constants import NULL_ADDRESS


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
    bond_operators,
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
    final_balance = 1
    mocker.patch.object(EthereumClient, "get_balance", side_effect=[0, final_balance])

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

    log_messages = []

    def log_trapper(event):
        log_messages.append(event["log_format"])

    expected_messages = [
        # iteration 1
        ("not funded with MATIC", "not bonded to a staking provider"),
        # iteration 2
        (
            f"is funded with {Web3.from_wei(final_balance, 'ether')} MATIC",
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
