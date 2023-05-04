import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from tests.mock.coordinator import MockCoordinatorAgent

FAKE_TRANSCRIPT = b'\x98\x00\x00\x00\x00\x00\x00\x00\x03\x00\x00\x00\x00\x00\x00\x00\xa9t\xedc\x88\xd26\xf6\x7f\n\xfbv\x8e_S0\xcc\xdad?\x96-~\xcf>O\xa2\x8bF.b\xe6r\x9f\x7f\x12m\rSm\x03\x8f\x86&|\x8e\x98\x98\xa2\x869\x93b\x95\xaa\xd6|\x12[\x92^H\xfb\xb6\x9ei\x0b\xb2\xa3\xa4\xbd\x17\xed&.\xb6\x10\x0b\xf4\r\x0c\xfa\x1e\x9b\xd8j\x9a\xbf2.dH>\x05\xc4\xe7\x96|\x1d\xe0N\xaf\xeeQ\xb6d\xab\x07\xdeI\x03\xc1\x12h\x84j\xcd5\x03\xa9~\x84<\x83\x93\x05ZL\x18U\xab\x8b\x1d\x12\xb7\x9e\x91\x9a\x93/\xc2\x82U\x9f\x88\x01\x00\x00\x00\x00\x00\x00\x04\x00\x00\x00\x00\x00\x00\x00\xb5-\n\xbc\xac\x05\x83\xf9D\x93h\xf7\x87\xf8\x15Mu\xcb=\xe4\xb3_4+\x9ey\x99\xff\xc8\x01;^\xfa\x06\x1f\xbe\x87\xd1\xf9\x95\x05\xa1\x82\xd8\xb7\xfc\xb4\x87\x07LG\x13\xb7\'\x95\x97\xe2\xb9\xcbZ.\xc1\xd0\xee\x8ac\xf4\xa0\xc42I\x02\xab\x97\x9d\xab\xc5\xe9\x9f\x03\xb2\x1bB@r\xb8\x97\x08[\xc8A\x84\xc1>h\xc7\x94\x80cO\xbc\xd4\xad\xedy\xbc\x81\xfe\x8aV-\xa6\xad7\xea=\xbf\xe1\xa1\x91\x99\x89H\xa4\xc0E\xaa\x07\x9b\xd5\x17\x1a>\x82\xc5\xcd\x1e\xce\xc3d?iH\x02\t\xc3e\xbf\xdd\x90\xd4x6\x0bC\xbf\xd6\xb8\x9cSw\x8c\xa0\xdc\x03\x8e\xd4\xab\xfd,\xd8\xac\x10E`?\xc5\x9f7\xc8\xea\xbby\x9d+\x1b\x90_\xe1)0*\xaa\xb8N\xdd\x81\xa2p\xa9\xe5\xcb|\xa1e!\x1e8\xf1H\x18\x9c\xa4\x8e\xfd\x0ey\xec\x8c\x01P")\xcde\x9b6\xd3\xc0\x99\xf4\xa9\x8a\xd0\xa5\x87\xc7\xc1:\xf1\x12J5*>\x9b\x82g\xb3\xd7\x1d\xc7^}\x06\xd5\xf7t\x9eH\x00\x85\xbd\xff"=\x1e\xb3&\x80\xe1\xed\xd3:\xd8\x17.\xfe\xed,\xf9\xc4\xa4\xf0\xb4\xdbY\x12\xa0\x1e\xc9\xc8\x99s&\xddn8\xb7nU\xb0l+o\xec\x90p\tGy\xde\x94\xe1U\xd3!\\N#\xcf\x95\x83i\x15\x91\xa9%\x01\xed\xd52\xd8\x1cr\x80\x12\x93\x7f5\xc7d?\\\xf0j6\xb4\xf7\x18\x80\x18\x16=\x8c\xa74z\xd4\x04Y\xa2\x1a\xde\xad\x9e\x82w\x01\xde\xb3\x1a\xf5\xf4\xa7z\x95\xb0=P\xb3 \xc8\x85`\x00\x00\x00\x00\x00\x00\x00\xa7\xe5\xabI`N\x00L\x84"\x02\xaeE\xde|\x0c3^}\xf9\xfeq\xb8(@U\xc9\xef\xae\xf88@\x8c{\xf2\xb0\xc0R<>\xc1#\x9c\xa3`\x93\xf5\xbf\x07\xb2\x92\xe1\xbd\x12\x04 z82\xc0\xab,q\x17\xfd\x08Pt\x19\x91\x8b\'\x00\x15\xad\xaa?\xa0N\xe4\xc9w\xce\xc1\x87\xb0\xfc\xa0\xa8\xf2\xb0H\x88\x14\xd4\xe8'


@pytest.fixture(scope='module')
def agent(mock_contract_agency) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(CoordinatorAgent, registry=None)
    return coordinator_agent


@pytest.fixture(scope='module')
def cohort(agent, ursulas):
    providers = []
    for u in ursulas[:4]:
        providers.append(u.checksum_address)
        agent._add_operator_to_staking_provider_mapping(
            {u.operator_address: u.checksum_address}
        )
    return [u.checksum_address for u in ursulas[:4]]


@pytest.fixture(scope='module')
def ursula(ursulas):
    return ursulas[1]


@pytest.fixture(scope='module')
def transacting_power(testerchain, alice):
    return TransactingPower(account=alice.transacting_power.account, signer=Web3Signer(testerchain.client))


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

    assert receipt['transactionHash']
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    return ritual_id


def test_perform_round_1(ursula, random_address, cohort):
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

    ursula.perform_round_2(ritual_id=0, timestamp=0)
