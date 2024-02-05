import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import RitualisticPower, TransactingPower
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain


@pytest.fixture(scope="module")
def agent(mock_contract_agency, ursulas) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None, blockchain_endpoint=MOCK_ETH_PROVIDER_URI
    )

    def mock_get_provider_public_key(provider, ritual_id):
        for ursula in ursulas:
            if ursula.checksum_address == provider:
                return ursula.public_keys(RitualisticPower)

    coordinator_agent.post_transcript = lambda *a, **kw: MockBlockchain.FAKE_ASYNX_TX
    coordinator_agent.post_aggregation = lambda *a, **kw: MockBlockchain.FAKE_ASYNX_TX
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
        tx = ursula.perform_round_1(
            ritual_id=0, authority=random_address, participants=cohort, timestamp=0
        )
        assert tx is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS
    )

    tx = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert tx is not None

    # ensure tx is tracked
    assert len(ursula.ritual_tracker.active_rituals) == 1

    # try again
    tx = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )

# TODO: check for clearance of tx hash on ritual tracker
#
#     # pending tx gets mined and removed from storage - receipt status is 1
#     mock_receipt = {"status": 1}
#     with patch.object(
#         agent.blockchain.client, "get_transaction_receipt", return_value=mock_receipt
#     ):
#         tx_hash = ursula.perform_round_1(
#             ritual_id=0, authority=random_address, participants=cohort, timestamp=0
#         )
#         # no execution since pending tx was present and determined to be mined
#         assert tx_hash is None
#         # tx hash removed since tx receipt was obtained - outcome moving
#         # forward is represented on contract
#         assert ursula.dkg_storage.get_transcript_txhash(ritual_id=0) is None
#
#     # reset tx hash
#     ursula.dkg_storage.store_transcript_txhash(ritual_id=0, txhash=original_tx_hash)
#
#     # pending tx gets mined and removed from storage - receipt
#     # status is 0 i.e. evm revert - so use contract state which indicates
#     # to submit transcript
#     mock_receipt = {"status": 0}
#     with patch.object(
#         agent.blockchain.client, "get_transaction_receipt", return_value=mock_receipt
#     ):
#         with patch.object(
#             agent, "post_transcript", lambda *args, **kwargs: HexBytes("A1B1")
#         ):
#             mock_tx_hash = ursula.perform_round_1(
#                 ritual_id=0, authority=random_address, participants=cohort, timestamp=0
#             )
#             # execution occurs because evm revert causes execution to be retried
#             assert mock_tx_hash == HexBytes("A1B1")
#             # tx hash changed since original tx hash removed due to status being 0
#             # and new tx hash added
#             # forward is represented on contract
#             assert ursula.dkg_storage.get_transcript_txhash(ritual_id=0) == mock_tx_hash
#             assert (
#                 ursula.dkg_storage.get_transcript_txhash(ritual_id=0)
#                 != original_tx_hash
#             )
#
#     # reset tx hash
#     ursula.dkg_storage.store_transcript_txhash(ritual_id=0, txhash=original_tx_hash)
#
#     # don't clear if tx hash mismatched
#     assert ursula.dkg_storage.get_transcript_txhash(ritual_id=0) is not None
#     assert not ursula.dkg_storage.clear_transcript_txhash(
#         ritual_id=0, txhash=HexBytes("abcd")
#     )
#     assert ursula.dkg_storage.get_transcript_txhash(ritual_id=0) is not None
# =======

    # participant already posted transcript
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
    )
    participant.transcript = bytes(random_transcript)

    # try submitting again
    tx = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )

    # participant no longer already posted aggregated transcript
    participant.transcript = bytes()
    tx = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )


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
        tx = ursula.perform_round_2(ritual_id=0, timestamp=0)

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS
    )

    mocker.patch("nucypher.crypto.ferveo.dkg.verify_aggregate")
    original_tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert original_tx_hash is not None

    tx = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert tx is not None

    # check tx hash tracking
    assert len(ursula.ritual_tracker.active_rituals) == 2

    # try again
    tx = ursula.perform_round_2(ritual_id=0, timestamp=0)
    # assert tx_hash is None  # no execution since pending tx already present

# TODO: check for clearance of tx hash on ritual tracker
#
#     # pending tx gets mined and removed from storage - receipt status is 1
#     mock_receipt = {"status": 1}
#     with patch.object(
#         agent.blockchain.client, "get_transaction_receipt", return_value=mock_receipt
#     ):
#         tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
#         # no execution since pending tx was present and determined to be mined
#         assert tx_hash is None
#         # tx hash removed since tx receipt was obtained - outcome moving
#         # forward is represented on contract
#         assert ursula.dkg_storage.get_aggregation_txhash(ritual_id=0) is None
#
#     # reset tx hash
#     ursula.dkg_storage.store_aggregation_txhash(ritual_id=0, txhash=original_tx_hash)
#
#     # pending tx gets mined and removed from storage - receipt
#     # status is 0 i.e. evm revert - so use contract state which indicates
#     # to submit transcript
#     mock_receipt = {"status": 0}
#     with patch.object(
#         agent.blockchain.client, "get_transaction_receipt", return_value=mock_receipt
#     ):
#         with patch.object(
#             agent, "post_aggregation", lambda *args, **kwargs: HexBytes("A1B1")
#         ):
#             mock_tx_hash = ursula.perform_round_2(ritual_id=0, timestamp=0)
#             # execution occurs because evm revert causes execution to be retried
#             assert mock_tx_hash == HexBytes("A1B1")
#             # tx hash changed since original tx hash removed due to status being 0
#             # and new tx hash added
#             # forward is represented on contract
#             assert (
#                 ursula.dkg_storage.get_aggregation_txhash(ritual_id=0) == mock_tx_hash
#             )
#             assert (
#                 ursula.dkg_storage.get_aggregation_txhash(ritual_id=0)
#                 != original_tx_hash
#             )
#
#     # reset tx hash
#     ursula.dkg_storage.store_aggregation_txhash(ritual_id=0, txhash=original_tx_hash)
#
#     # don't clear if tx hash mismatched
#     assert not ursula.dkg_storage.clear_aggregated_txhash(
#         ritual_id=0, txhash=HexBytes("1234")
#     )
#     assert ursula.dkg_storage.get_aggregation_txhash(ritual_id=0) is not None

    # participant already posted aggregated transcript
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
    )
    participant.aggregated = True

    # try submitting again
    tx = ursula.perform_round_2(ritual_id=0, timestamp=0)
    # assert tx_hash is None  # no execution performed

    # participant no longer already posted aggregated transcript
    participant.aggregated = False
    tx = ursula.perform_round_2(ritual_id=0, timestamp=0)
    # assert tx is not None  # execution occurs
