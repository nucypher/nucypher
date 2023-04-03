import os

import pytest
from eth_utils import keccak

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.deployers import CoordinatorDeployer
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


@pytest.fixture(scope='module')
def agent(testerchain, test_registry) -> CoordinatorAgent:
    origin, *everybody_else = testerchain.client.accounts
    coodinator_deployer = CoordinatorDeployer(registry=test_registry)
    tpower = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    coodinator_deployer.deploy(transacting_power=tpower)
    coordinator_agent = coodinator_deployer.make_agent()
    return coordinator_agent


@pytest.fixture(scope='module')
def transcript(agent):
    return os.urandom(32)


@pytest.fixture(scope='module')
def aggregated_transcript(agent):
    return os.urandom(32)


@pytest.fixture(scope='module')
def cohort(ursulas):
    deployer, someone, *everybody_else = testerchain.stake_providers_accounts
    return [someone]


@pytest.fixture(scope='module')
def ursula(cohort):
    return cohort[0]


@pytest.fixture(scope='module')
def transacting_power(testerchain, ursula):
    return TransactingPower(account=ursula, signer=Web3Signer(testerchain.client))


def test_coordinator_properties(agent):
    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == CoordinatorAgent.contract_name
    assert not agent._proxy_name  # not upgradeable


def test_initiate_ritual(agent, deploy_contract, cohort, transacting_power):
    number_of_rituals = agent.number_of_rituals()
    assert number_of_rituals == 0

    receipt = agent.initiate_ritual(
        nodes=cohort,
        transacting_power=transacting_power
    )
    assert receipt['status'] == 1
    start_ritual_event = agent.contract.events.StartRitual().processReceipt(receipt)
    assert start_ritual_event[0]['args']['nodes'] == cohort

    number_of_rituals = agent.number_of_rituals()
    assert number_of_rituals == 1
    ritual_id = number_of_rituals - 1

    ritual = agent.get_ritual(ritual_id)
    assert ritual.initiator == transacting_power.account

    participants = agent.get_participants(ritual_id)
    assert [p.node for p in participants] == cohort


def test_post_transcript(agent, deploy_contract, transcript, transacting_power):
    ritual_id = agent.number_of_rituals() - 1
    receipt = agent.post_transcript(
        ritual_id=ritual_id,
        node_index=0,
        transcript=transcript,
        transacting_power=transacting_power
    )
    assert receipt['status'] == 1
    post_transcript_events = agent.contract.events.TranscriptPosted().processReceipt(receipt)
    assert len(post_transcript_events) == 1
    event = post_transcript_events[0]
    assert event['args']['ritualId'] == ritual_id
    assert event['args']['transcriptDigest'] == keccak(transcript)

    participants = agent.get_participants(ritual_id)
    assert [p.transcript for p in participants] == [transcript]



def test_post_aggregation(agent, deploy_contract, aggregated_transcript, transacting_power):
    ritual_id = agent.number_of_rituals() - 1
    receipt = agent.post_aggregation(
        ritual_id=ritual_id,
        node_index=0,
        aggregated_transcript=aggregated_transcript,
        transacting_power=transacting_power
    )
    assert receipt['status'] == 1

    post_aggregation_events = agent.contract.events.AggregationPosted().processReceipt(receipt)
    assert len(post_aggregation_events) == 1
    event = post_aggregation_events[0]
    assert event['args']['ritualId'] == ritual_id
    assert event['args']['aggregatedTranscriptDigest'] == keccak(aggregated_transcript)

    participants = agent.get_participants(ritual_id)
    assert all([p.aggregated for p in participants])
    # assert [p.transcript for p in participants] == [keccak(aggregated_transcript)]
