import pytest
from hexbytes import HexBytes

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import RitualisticPower, TransactingPower
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.mock.coordinator import MockCoordinatorAgent


@pytest.fixture(scope="module")
def agent(mock_contract_agency, ursulas) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None, blockchain_endpoint=MOCK_ETH_PROVIDER_URI
    )

    def mock_get_provider_public_key(provider, ritual_id):
        for ursula in ursulas:
            if ursula.checksum_address == provider:
                return ursula.public_keys(RitualisticPower)

    coordinator_agent.post_transcript = lambda *args, **kwargs: HexBytes("deadbeef")
    coordinator_agent.post_aggregation = lambda *args, **kwargs: HexBytes("deadbeef")
    coordinator_agent.get_provider_public_key = mock_get_provider_public_key
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
        Coordinator.Participant(
            index=i,
            provider=c,
        )
        for i, c in enumerate(cohort)
    ]

    init_timestamp = 123456
    end_timestamp = init_timestamp + duration
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    ritual = Coordinator.Ritual(
        id=ritual_id,
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

    assert receipt["transactionHash"]
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
    for i, checksum_address in enumerate(cohort):
        participants[checksum_address] = Coordinator.Participant(
            index=i,
            provider=checksum_address,
        )

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100
    ritual = Coordinator.Ritual(
        id=0,
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
    agent.get_participant = lambda ritual_id, provider, transcript: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        Coordinator.RitualStatus.NON_INITIATED,
        Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS,
        Coordinator.RitualStatus.ACTIVE,
        Coordinator.RitualStatus.EXPIRED,
        Coordinator.RitualStatus.DKG_TIMEOUT,
        Coordinator.RitualStatus.DKG_INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        tx_hash = ursula.perform_round_1(
            ritual_id=0, authority=random_address, participants=cohort, timestamp=0
        )
        assert tx_hash is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS
    )

    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is not None

    # ensure tx hash is stored
    assert ursula.dkg_storage.get_transcript_txhash(ritual_id=0) == tx_hash

    # try again
    tx_hash = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx_hash is None  # no execution since pending tx already present

    # clear tx hash
    ursula.dkg_storage.store_transcript_txhash(ritual_id=0, txhash=None)

    # participant already posted transcript
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
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
    for i, checksum_address in enumerate(cohort):
        participant = Coordinator.Participant(
            index=i,
            transcript=bytes(random_transcript),
            provider=checksum_address,
        )

        participants[checksum_address] = participant

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100

    ritual = Coordinator.Ritual(
        id=0,
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
    agent.get_participant = lambda ritual_id, provider, transcript: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        Coordinator.RitualStatus.NON_INITIATED,
        Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS,
        Coordinator.RitualStatus.ACTIVE,
        Coordinator.RitualStatus.EXPIRED,
        Coordinator.RitualStatus.DKG_TIMEOUT,
        Coordinator.RitualStatus.DKG_INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
        assert tx_hash is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS
    )

    mocker.patch("nucypher.crypto.ferveo.dkg.verify_aggregate")
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is not None

    # check tx hash
    assert ursula.dkg_storage.get_aggregation_txhash(ritual_id=0) == tx_hash

    # try again
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is None  # no execution since pending tx already present

    # clear tx hash
    ursula.dkg_storage.store_aggregation_txhash(ritual_id=0, txhash=None)

    # participant already posted aggregated transcript
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
    )
    participant.aggregated = True

    # try submitting again
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is None  # no execution performed

    # participant no longer already posted aggregated transcript
    participant.aggregated = False
    tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx_hash is not None  # execution occurs
