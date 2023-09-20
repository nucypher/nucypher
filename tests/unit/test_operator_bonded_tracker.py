import pytest
import pytest_twisted
from twisted.internet import threads

from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.trackers.bonding import OperatorBondedTracker


@pytest_twisted.inlineCallbacks
def test_operator_never_bonded(mocker, get_random_checksum_address):
    ursula = mocker.Mock()
    operator_address = get_random_checksum_address()
    ursula.operator_address = operator_address

    application_agent = mocker.Mock()
    application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS

    mocker.patch.object(ContractAgency, 'get_agent', return_value=application_agent)

    tracker = OperatorBondedTracker(ursula=ursula)
    try:
        d = threads.deferToThread(tracker.start)
        yield d

        with pytest.raises(OperatorBondedTracker.OperatorNoLongerBonded):
            d = threads.deferToThread(tracker.run)
            yield d
    finally:
        application_agent.get_staking_provider_from_operator.assert_called_once()
        ursula.stop.assert_called_once_with(halt_reactor=True)  # stop entire reactor
        tracker.stop()


@pytest_twisted.inlineCallbacks
def test_operator_bonded_but_becomes_unbonded(mocker, get_random_checksum_address):
    ursula = mocker.Mock()
    operator_address = get_random_checksum_address()
    ursula.operator_address = operator_address

    application_agent = mocker.Mock()
    staking_provider = get_random_checksum_address()
    application_agent.get_staking_provider_from_operator.return_value = staking_provider

    mocker.patch.object(ContractAgency, 'get_agent', return_value=application_agent)

    tracker = OperatorBondedTracker(ursula=ursula)
    try:
        d = threads.deferToThread(tracker.start)
        yield d

        # bonded
        for i in range(1, 10):
            d = threads.deferToThread(tracker.run)
            yield d
            assert application_agent.get_staking_provider_from_operator.call_count == i, "check for operator bonded called"
            ursula.stop.assert_not_called()

        # becomes unbonded
        application_agent.get_staking_provider_from_operator.return_value = NULL_ADDRESS
        with pytest.raises(OperatorBondedTracker.OperatorNoLongerBonded):
            d = threads.deferToThread(tracker.run)
            yield d
    finally:
        ursula.stop.assert_called_once_with(halt_reactor=True)  # stop entire reactor
        tracker.stop()


def test_operator_handle_errors(mocker, get_random_checksum_address):
    ursula = mocker.Mock()
    tracker = OperatorBondedTracker(ursula=ursula)

    f = mocker.Mock()
    f.getTraceback.return_value = "traceback"
    f.raiseException.side_effect = OperatorBondedTracker.OperatorNoLongerBonded()

    # inconsequential exception so no exception raised
    f.check.return_value = False
    tracker.handle_errors(failure=f)  # no exception

    # exception that is cared about, so exception raised
    f.check.return_value = True
    with pytest.raises(OperatorBondedTracker.OperatorNoLongerBonded):
        tracker.handle_errors(failure=f)


@pytest.mark.parametrize(
    "traceback",
    (
        "just some text",
        "text with {",
        "test with }",
        "test with {a} pair of curly braces" "test with {more} curly } braces {",
    ),
)
def test_operator_bonded_clean_traceback(traceback, mocker):
    f = mocker.Mock()
    f.getTraceback.return_value = traceback
    result = OperatorBondedTracker.clean_traceback(f)
    assert "{" not in result
    assert "}" not in result
