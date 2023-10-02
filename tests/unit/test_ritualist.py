import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.mock.coordinator import MockCoordinatorAgent


@pytest.fixture(scope="module")
def agent(mock_contract_agency) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None, blockchain_endpoint=MOCK_ETH_PROVIDER_URI
    )
    return coordinator_agent


@pytest.fixture(scope="module")
def ursula(ursulas):
    return ursulas[1]


@pytest.fixture(scope="module")
def cohort(ursulas):
    return [u.staking_provider_address for u in ursulas[:4]]


@pytest.fixture(scope="module")
def transacting_power(testerchain, alice):
    return TransactingPower(
        account=alice.transacting_power.account, signer=Web3Signer(testerchain.client)
    )


def test_initiate_ritual(
    agent: CoordinatorAgent, cohort, transacting_power, get_random_checksum_address
):
    # any value will do
    global_allow_list = get_random_checksum_address()

    duration = 100
    receipt = agent.initiate_ritual(
        authority=transacting_power.account,
        access_controller=global_allow_list,
        providers=cohort,
        duration=duration,
        transacting_power=transacting_power,
    )

    participants = [
        CoordinatorAgent.Ritual.Participant(
            provider=c,
        )
        for c in cohort
    ]

    init_timestamp = 123456
    end_timestamp = init_timestamp + duration
    ritual = CoordinatorAgent.Ritual(
        initiator=transacting_power.account,
        authority=transacting_power.account,
        access_controller=global_allow_list,
        dkg_size=4,
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(dkg_size=4),
        init_timestamp=123456,
        end_timestamp=end_timestamp,
        participants=participants,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants

    assert receipt["transactionHash"]
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    return ritual_id


def test_perform_round_1(
    ursula,
    random_address,
    cohort,
    agent,
    random_transcript,
    get_random_checksum_address,
):
    participants = dict()
    for checksum_address in cohort:
        participants[checksum_address] = CoordinatorAgent.Ritual.Participant(
            provider=checksum_address,
        )

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100
    ritual = CoordinatorAgent.Ritual(
        initiator=random_address,
        authority=random_address,
        access_controller=get_random_checksum_address(),
        dkg_size=4,
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(dkg_size=4),
        init_timestamp=init_timestamp,
        end_timestamp=end_timestamp,
        total_transcripts=4,
        participants=list(participants.values()),
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants
    agent.get_participant_from_provider = lambda ritual_id, provider: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        CoordinatorAgent.Ritual.Status.NON_INITIATED,
        CoordinatorAgent.Ritual.Status.AWAITING_AGGREGATIONS,
        CoordinatorAgent.Ritual.Status.FINALIZED,
        CoordinatorAgent.Ritual.Status.TIMEOUT,
        CoordinatorAgent.Ritual.Status.INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        tx_hash = ursula.perform_round_1(
            ritual_id=0, authority=random_address, participants=cohort, timestamp=0
        )
        assert tx_hash is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: CoordinatorAgent.Ritual.Status.AWAITING_TRANSCRIPTS
    )

    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is not None

    # ensure tx hash is stored
    assert ursula.dkg_storage.get_transcript_receipt(ritual_id=0) == tx_hash

    # try again
    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is None  # no execution since pending tx already present

    # clear tx hash
    ursula.dkg_storage.store_transcript_receipt(ritual_id=0, txhash_or_receipt=None)

    # participant already posted transcript
    participant = agent.get_participant_from_provider(
        ritual_id=0, provider=ursula.checksum_address
    )
    participant.transcript = bytes(random_transcript)

    # try submitting again
    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is None  # no execution performed

    # participant no longer already posted aggregated transcript
    participant.transcript = bytes()
    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is not None  # execution occurs


def test_perform_round_2(
    ursula,
    cohort,
    transacting_power,
    agent,
    mocker,
    random_transcript,
    get_random_checksum_address,
):
    participants = dict()
    for checksum_address in cohort:
        participant = CoordinatorAgent.Ritual.Participant(
            transcript=bytes(random_transcript),
            provider=checksum_address,
        )

        participants[checksum_address] = participant

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100

    ritual = CoordinatorAgent.Ritual(
        initiator=transacting_power.account,
        authority=transacting_power.account,
        access_controller=get_random_checksum_address(),
        dkg_size=len(cohort),
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(
            dkg_size=len(cohort)
        ),
        init_timestamp=init_timestamp,
        end_timestamp=end_timestamp,
        total_transcripts=len(cohort),
        participants=list(participants.values()),
    )

    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants
    agent.get_participant_from_provider = lambda ritual_id, provider: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        CoordinatorAgent.Ritual.Status.NON_INITIATED,
        CoordinatorAgent.Ritual.Status.AWAITING_TRANSCRIPTS,
        CoordinatorAgent.Ritual.Status.FINALIZED,
        CoordinatorAgent.Ritual.Status.TIMEOUT,
        CoordinatorAgent.Ritual.Status.INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
        assert tx_hash is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: CoordinatorAgent.Ritual.Status.AWAITING_AGGREGATIONS
    )

    mocker.patch("nucypher.crypto.ferveo.dkg.verify_aggregate")
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is not None

    # check tx hash
    assert ursula.dkg_storage.get_aggregated_transcript_receipt(ritual_id=0) == tx_hash

    # try again
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is None  # no execution since pending tx already present

    # clear tx hash
    ursula.dkg_storage.store_aggregated_transcript_receipt(
        ritual_id=0, txhash_or_receipt=None
    )

    # participant already posted aggregated transcript
    participant = agent.get_participant_from_provider(
        ritual_id=0, provider=ursula.checksum_address
    )
    participant.aggregated = True

    # try submitting again
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is None  # no execution performed

    # participant no longer already posted aggregated transcript
    participant.aggregated = False
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is not None  # execution occurs
