import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from tests.mock.coordinator import MockCoordinatorAgent

FAKE_TRANSCRIPT = b'\x98\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\xae\xdb_-\xeaj\x9bz\xdd\xd6\x98\xf8\xf91A\xc1\x8f;\x13@\x89\xcb\xcf>\x86\xc4T\xfb\x0c\x1ety\x8b\xd8mSkk\xbb\xcaU\xe5]v}E\xfa\xbc\xae\xb6\xa1\xf4e\x19\x86\xf2L\xcaZj\x03]h:\xbfP\x03Q\x8c\x95e\xe0c\xaa\xc2\xb4\xbby}\xecW%\xdet\xc8\xfc\xe7ky\xe5\xf6\xe9\xf5\x05\xe5\xdf\x81\x9bx\x18\xa4\x15\x85\xdeA9\x9f\x99\xceQ\xb0\xd0&\x9a\xa7\xaed&\x99\xdc\xa7\xfeLM\x01\x02\x87\xc8\x14$\x89"kA\x0b\x91\t\x1e\x1c/f\x00N,\x88\x01\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\xab\x0f\tFA\xdcB\xd4\xb3\x08\xd7IVkmw6za\xb6)\x13\x014]f.\xa1\xcd\xe27\xee\xc0\x95\xf6\xa4\x12\xa9\x19\x94\xed\x05\xffF\x81\xb2\xb2\xcb\x06\xaf-\xe4\xb5\x98\xbd\x81\x0f\xb8\xb7\xa1<\xf6/\xe5\xa4\x11\x83}\xfaH\x15\x80h\n\xe7\xc6\xc2\xb3\xd5{dH\xeb\x1e]v\xb4\x88v\x88\xb7N1\xff\x80\xd0\x88\x04.\x00\x82K\x1e\x96\xa0\xbd}X\xbb{?6\xeb\xe7\rg\x03\xeeG\x01\x10^\xee\x9cH\x94[\x9d8s\xa3\xb6\x8f\xfc\xf1\xdf\x01m\xf9\x08_N\xb5-\x16O\x89n\x95\xf3\x8b[\x1f&Yk?*\x07\x8fQ\x98\x85\xd5\xc1YL\xe0CB\xb2"!\x8d,\x90Q7\xca\x9c\x0e\xb2\x7f\xb0\xe1\xc8\xdd\xe7\xe1\xe4\x14\xb3\xa6\xb4\x8e\x8b\xed\xacM\xc3\x9d\xc4|U\x93k\x17\xac\x14\x86\x16\xd7\xebk\xbd{\xad}\x87\x13Y\x83\x9d\x88\x1e\x1b4\xa7r\xa6\x80\xbf\xf0\x15\x99\x11Q\xdb\xeb\xdf\x15ns\xc6\x85\xb3\x1d\xf5j\xc5\x87`=OD\x86\x86\x08\x8d\xb6\x0b\xec\x1d\x15\xc9\x93\x9a\xed\xa3\xe2\x96\xa4\xa2b\xa6\xa5h\xb0\xbb4\xb3\x0c\xa5\xdcu\x1f{\xb9\xaf\xd0W\xe1\xa3&\xa8\xb5\xea\xe5c\xfd\xc7?\xbdLg\xb3\xae\xb9\xb8*\xfc\xd5\xa6\xeeI\x15v\xdc\xa2`1VZ\xb5\x1c_`\x86\xbe{\xef\xae\t\xf2\xa9N\x00\x9a\xa1F\x84\xb2\xe3\xbc\xfa\xf7I\xee\xe8[~\x99;i\xfc%\xa8\x80\x80\x8e%\'\x9c+\x9c\xa9\x13R!\x80w\xc0\xda[\x84\xf6X\xfe\xc2\xe3\x0f\x94-\xbb`\x00\x00\x00\x00\x00\x00\x00\x93\xff\x1e\x1b\x15;e\xfe}\x83v K\xf9\r\xc9\xad\x9d\xddN\xcd\xcaWq\xfa\x8e\x98sn\x9b~t\x01 =p\xe5\xb1\x7f"!\xb4\xb9\xc9W\x90\x86\x80\x17\nm\xa0\x8dD\xb5\xaf\xfc\xa5\xf5%V]\xb9\x89a@\xe5\x0c@#%x\xecW\xed\xb0a\x98\x1a!C\x80B@{\xf0\xffJ{\xa3\xeayDP\'u'


@pytest.fixture(scope="module")
def agent(mock_contract_agency) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None
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

    ursula.ritual_tracker.refresh(fetch_rituals=[0])
    ursula.perform_round_1(
        ritual_id=0, initiator=random_address, participants=cohort, timestamp=0
    )


def test_perform_round_2(ursula, cohort, transacting_power, agent, mocker):
    participants = [
        CoordinatorAgent.Ritual.Participant(
            provider=c, aggregated=False, transcript=FAKE_TRANSCRIPT
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
