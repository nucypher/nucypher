import os

import pytest
from eth_utils import keccak
from nucypher_core import SessionStaticSecret

from nucypher.blockchain.eth.agents import CoordinatorAgent


@pytest.fixture(scope='module')
def agent(coordinator_agent) -> CoordinatorAgent:
    return coordinator_agent


@pytest.fixture(scope='module')
def transcripts():
    return [os.urandom(32), os.urandom(32)]


@pytest.mark.usefixtures("ursulas")
@pytest.fixture(scope="module")
def cohort(accounts):
    cohort_providers = [accounts.stake_provider_wallets[i].address for i in range(2)]
    cohort_providers.sort()
    return cohort_providers


@pytest.fixture(scope='module')
def cohort_ursulas(cohort, taco_application_agent):
    ursulas_for_cohort = []
    for provider in cohort:
        operator = taco_application_agent.get_operator_from_staking_provider(provider)
        ursulas_for_cohort.append(operator)
    return ursulas_for_cohort


def test_coordinator_properties(agent):
    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == CoordinatorAgent.contract_name


@pytest.mark.usefixtures("ursulas")
def test_initiate_ritual(
    accounts,
    agent,
    cohort,
    get_random_checksum_address,
    global_allow_list,
    ritual_token,
    testerchain,
    initiator,
):

    number_of_rituals = agent.number_of_rituals()
    assert number_of_rituals == 0

    duration = 60 * 60 * 24
    amount = agent.get_ritual_initiation_cost(cohort, duration)

    # Approve the ritual token for the coordinator agent to spend
    # TODO: This is a hack to get the initiator wallet to be an ape account for the ritual token tx
    ape_initiator = accounts.ape_accounts[accounts.accounts.index(initiator.wallet)]
    ritual_token.approve(
        agent.contract_address,
        amount,
        sender=ape_initiator,
    )

    authority = get_random_checksum_address()
    receipt = agent.initiate_ritual(
        providers=cohort,
        authority=authority,
        duration=duration,
        access_controller=global_allow_list.address,
        wallet=initiator.wallet,
    )
    assert receipt['status'] == 1
    start_ritual_event = agent.contract.events.StartRitual().process_receipt(receipt)
    assert start_ritual_event[0]["args"]["participants"] == cohort

    number_of_rituals = agent.number_of_rituals()
    assert number_of_rituals == 1
    ritual_id = number_of_rituals - 1

    ritual = agent.get_ritual(ritual_id)
    assert ritual.authority == authority

    participants = agent.get_participants(ritual_id)
    assert [p.provider for p in participants] == cohort

    assert (
        agent.get_ritual_status(ritual_id=ritual_id)
        == agent.Ritual.Status.DKG_AWAITING_TRANSCRIPTS
    )

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert ritual_dkg_key is None  # no dkg key available until ritual is completed


def test_post_transcript(agent, transcripts, cohort_ursulas, accounts):
    ritual_id = agent.number_of_rituals() - 1
    for i, wallet in enumerate(accounts.ursula_wallets[:len(cohort_ursulas)]):
        receipt = agent.post_transcript(
            ritual_id=ritual_id,
            transcript=transcripts[i],
            wallet=wallet,
        )
        assert receipt["status"] == 1
        post_transcript_events = (
            agent.contract.events.TranscriptPosted().process_receipt(receipt)
        )
        # assert len(post_transcript_events) == 1
        event = post_transcript_events[0]
        assert event["args"]["ritualId"] == ritual_id
        assert event["args"]["transcriptDigest"] == keccak(transcripts[i])

    participants = agent.get_participants(ritual_id)
    assert [p.transcript for p in participants] == transcripts

    assert (
        agent.get_ritual_status(ritual_id=ritual_id)
        == agent.Ritual.Status.DKG_AWAITING_AGGREGATIONS
    )

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert ritual_dkg_key is None  # no dkg key available until ritual is completed


def test_post_aggregation(
    agent, aggregated_transcript, dkg_public_key, accounts, cohort, cohort_ursulas
):
    ritual_id = agent.number_of_rituals() - 1
    participant_public_keys = {}
    for i, wallet in enumerate(accounts.ursula_wallets[:len(cohort_ursulas)]):
        participant_public_key = SessionStaticSecret.random().public_key()
        receipt = agent.post_aggregation(
            ritual_id=ritual_id,
            aggregated_transcript=aggregated_transcript,
            public_key=dkg_public_key,
            participant_public_key=participant_public_key,
            wallet=wallet,
        )
        participant_public_keys[cohort[i]] = participant_public_key
        assert receipt["status"] == 1

        post_aggregation_events = (
            agent.contract.events.AggregationPosted().process_receipt(receipt)
        )
        # assert len(post_aggregation_events) == 1
        event = post_aggregation_events[0]
        assert event["args"]["ritualId"] == ritual_id
        assert event["args"]["aggregatedTranscriptDigest"] == keccak(
            bytes(aggregated_transcript)
        )

    participants = agent.get_participants(ritual_id)
    for p in participants:
        assert p.aggregated
        assert p.decryption_request_static_key == bytes(
            participant_public_keys[p.provider]
        )

    ritual = agent.get_ritual(ritual_id)
    assert ritual.participant_public_keys == participant_public_keys

    assert agent.get_ritual_status(ritual_id=ritual_id) == agent.Ritual.Status.ACTIVE

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert bytes(ritual_dkg_key) == bytes(dkg_public_key)
