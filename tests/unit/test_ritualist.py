import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.mock.coordinator import MockCoordinatorAgent


@pytest.fixture(scope="module")
def agent(mock_contract_agency) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None, provider_uri=MOCK_ETH_PROVIDER_URI
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


def test_initiate_ritual(agent: CoordinatorAgent, cohort, transacting_power):
    receipt = agent.initiate_ritual(
        providers=cohort, transacting_power=transacting_power
    )

    participants = [
        CoordinatorAgent.Ritual.Participant(
            provider=c,
        )
        for c in cohort
    ]

    ritual = CoordinatorAgent.Ritual(
        initiator=transacting_power.account,
        dkg_size=4,
        init_timestamp=123456,
        participants=participants,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants

    assert receipt["transactionHash"]
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    return ritual_id


def test_perform_round_1(ursula, random_address, cohort, agent):
    participants = [
        CoordinatorAgent.Ritual.Participant(
            provider=c,
        )
        for c in cohort
    ]
    ritual = CoordinatorAgent.Ritual(
        initiator=random_address,
        dkg_size=4,
        init_timestamp=123456,
        total_transcripts=4,
        participants=participants,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants

    agent.get_participant_from_provider = lambda *args, **kwargs: participants[0]

    ursula.perform_round_1(
        ritual_id=0, initiator=random_address, participants=cohort, timestamp=0
    )


def test_perform_round_2(
    ursula, cohort, transacting_power, agent, mocker, random_transcript
):
    participants = [
        CoordinatorAgent.Ritual.Participant(
            provider=c, aggregated=False, transcript=bytes(random_transcript)
        )
        for c in cohort
    ]
    ritual = CoordinatorAgent.Ritual(
        initiator=transacting_power.account,
        dkg_size=4,
        init_timestamp=123456,
        total_transcripts=4,
        participants=participants,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants
    agent.get_ritual_status = lambda *args, **kwargs: 2

    mocker.patch("nucypher.crypto.ferveo.dkg.verify_aggregate")
    ursula.perform_round_2(ritual_id=0, timestamp=0)
