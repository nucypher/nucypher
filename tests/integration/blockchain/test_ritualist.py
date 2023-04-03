import pytest

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower

FAKE_TRANSCRIPT = b'\x02\x00\x00\x00\x00\x00\x00\x00I\xfc\xf1\xe7 u\xa4=\xda\xc7\xb8\t\xf4:\x1e\xf9$\xff\xa9\x13\x92EH%>\xf1\xdb\'\x8e#=\x0c\x85\xb3\xbd\x18\xca\xe3\x9d\x12\x90\x90A\xfc\xab\x06\x06\x84?\xe80\x9e\x95\x01\x9av\xbd\xcf[\xb0v\xec\xe6\x12L\xc6\x1aVr`n\xa2n\x12q\x9cmo\x14\xe9[r\xabJ\x16\x97\\Z#>B\x1fw\x1c\xec\x87\x04\x00\x00\x00\x00\x00\x00\x00\xab\x1e\x90\x11]\xca\xac\xc1=7N\x10\x7fjZ\x928\xe6y\xf8\x86+\xde\x94z\x89R\xf3<\xb5n<s\r\xe2\x99\x91p\x1a\xc8\xb0\xdd\xc7\xd6\xd3\x9b\x10\r\xb78P\xbed\xb9\xd5\x9a\xa4T\xde\xfe_\x9d\x08\xa5/\xdb.uJ\'\xf02\x94@\x13\xff\xf2\xbc\x04\xe5B\xcb\x0cE\x7f<M\x88O_\xf6XK\xb2\xa3\x89am\xea`\x99;\x82A\x94\x1b2\xae\xff\x07tG\xd1[\x88\x01\xc9\xf9=\xf7\x89\x0b2\xf2V\x87\x1f#\xb6y\x9f\xd9\xe8X\xd7\x8a*4\x9b\xf5\xcb\x02\xe9\x08\xcd\x98\xf5\xf0\x99\x15x\xa1\x9c3kj\x9c\x8b\xe5\xcd\x9c\xd3A\x0fR1\xa9oT\x9c\xdf\x87\xaa\xcd\xa3\x11\xe7)u\xb0CK\x1e\n\r\xb3)\\5c\x86\x02\xa1\xb6\xc1\'\xf3\xe5 \x12\x88\x02h\xa2\x14\x1a\xd7\x02\xbc\x03%\x18\x1b!\xddY\xb5 67JS\xf1\xdc\x025X\xa9\xe0\x94\x02&\x8fC\x8b\xd6\xb9\xc0:\x18\x8b\xa3\xee*~\xa2\x8f\x83\xb8mR\xf1\xc9h\xc9\x04\x137\x9a\x0f``\xb6\xf4\xaf\xff\xf2\'\xe2Bdp\x1fg9\xf3\xb5\xee\xa3\x1a\xedy!\xf9\x81R\x91\x08`\xed\xf07\x88\x02\xdfl\x85\xc2\xbe]\xbc\xe1l\xb72\xc7`\x91-0n\xfd\x80G\x1f\xf9\xe7\n\x12S\xbdJ\xd2\xfb$M\x89*\x8bl\xb9\x1aWR\xe7\x15\xcdA\x04\xd6\x99\xda\xf6\xa2\t\xb4\xe1a\x16\x94\xc3\xf30\xe45b\x9a\xe6$\xc8\x04\xd4z\xa9\xb7\\\x05D\x0c(L\x17\xb5\xbe\xa7\xe0\n\x11\xa6\xb3\x15\\U\x12\x86\xad[br\xba\xa8|R%\x97\xd4c\xa5\xce`\xeb\xb7n\x0e\xb2\xa0+(\xa9\x065\x83\xf9D\xfb\xcd\xf2& \xc1\x15\xd4\x1b\x03\x9f\xfc7\xda\x85\xc4K\x0b\xfc\xcf\x80\'s&\xe6A\xaf5\xdc\x7f\x1b\xec\xcftPf)ag\x8e\xa5\xc8*\xfe\xfb\xde\xf7R9\x86p([\x8a\xbd"\xebQHA\x7f\xf5rlg\x03'


@pytest.fixture(scope='module')
def agent(mock_contract_agency) -> CoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(CoordinatorAgent, registry=None)
    return coordinator_agent


@pytest.fixture(scope='module')
def cohort(ursulas):
    return [u.checksum_address for u in ursulas[1:]]


@pytest.fixture(scope='module')
def ursula(ursulas):
    return ursulas[1]


@pytest.fixture(scope='module')
def transacting_power(testerchain, alice):
    return TransactingPower(account=alice.transacting_power.account, signer=Web3Signer(testerchain.client))


def test_initiate_ritual(agent: CoordinatorAgent, deploy_contract, cohort, transacting_power):
    receipt = agent.initiate_ritual(
        nodes=cohort,
        transacting_power=transacting_power
    )

    participants = [CoordinatorAgent.Ritual.Participant(
        node=c,
        aggregated=False,
        transcript=bytes()
    ) for c in cohort]

    ritual = CoordinatorAgent.Ritual(
        id=0,
        initiator=transacting_power.account,
        dkg_size=3,
        init_timestamp=123456,
        total_transcripts=0,
        total_aggregations=0,
        aggregated_transcript_hash=b'FAKE',
        aggregation_mismatch=False,
        aggregated_transcript=b'FAKE',
        public_key=bytes(),
        participants=participants,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participants = lambda *args, **kwargs: participants

    assert receipt['transactionHash']
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    return ritual_id


def test_perform_round_1(ursula):
    ursula.ritual_tracker.refresh(fetch_rituals=[0])
    ursula.perform_round_1(ritual_id=0, timestamp=0)


def test_perform_round_2(ursula, cohort, transacting_power, agent, mocker):
    mocker.patch('nucypher.crypto.ferveo.dkg._validate_pvss_aggregated', return_value=True)
    participants = [CoordinatorAgent.Ritual.Participant(
        node=c,
        aggregated=False,
        transcript=FAKE_TRANSCRIPT
    ) for c in cohort]
    agent.get_participants = lambda *args, **kwargs: participants
    ursula.coordinator_agent.get_ritual_status = lambda *args, **kwargs: 2
    ursula.ritual_tracker.refresh(fetch_rituals=[0])
    ursula.perform_round_2(ritual_id=0, timestamp=0)
