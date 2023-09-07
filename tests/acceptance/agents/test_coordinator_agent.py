import os

import pytest
from eth_utils import keccak
from nucypher_core import SessionStaticSecret
from web3 import Web3

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    CoordinatorAgent,
    PREApplicationAgent,
)
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from tests.constants import TEST_ETH_PROVIDER_URI


@pytest.fixture(scope='module')
def agent(testerchain, test_registry) -> CoordinatorAgent:
    coordinator_agent = ContractAgency.get_agent(
        CoordinatorAgent, registry=test_registry, provider_uri=TEST_ETH_PROVIDER_URI
    )
    return coordinator_agent


@pytest.fixture(scope='module')
def transcripts():
    return [os.urandom(32), os.urandom(32)]


@pytest.mark.usefixtures("ursulas")
@pytest.fixture(scope="module")
def cohort(testerchain, staking_providers):
    # "ursulas" fixture is needed to set provider public key
    deployer, cohort_provider_1, cohort_provider_2, *everybody_else = staking_providers
    cohort_providers = [cohort_provider_1, cohort_provider_2]
    cohort_providers.sort()  # providers must be sorted
    return cohort_providers


@pytest.fixture(scope='module')
def cohort_ursulas(cohort, test_registry):
    ursulas_for_cohort = []
    application_agent = ContractAgency.get_agent(
        PREApplicationAgent,
        registry=test_registry,
        provider_uri=TEST_ETH_PROVIDER_URI,
    )
    for provider in cohort:
        operator = application_agent.get_operator_from_staking_provider(provider)
        ursulas_for_cohort.append(operator)

    return ursulas_for_cohort


@pytest.fixture(scope='module')
def transacting_powers(testerchain, cohort_ursulas):
    return [
        TransactingPower(account=ursula, signer=Web3Signer(testerchain.client))
        for ursula in cohort_ursulas
    ]


@pytest.fixture()
def initiator(testerchain, alice, ritual_token, deployer_account):
    """Returns the Initiator, funded with RitualToken"""
    # transfer ritual token to alice
    tx = ritual_token.functions.transfer(
        alice.transacting_power.account,
        Web3.to_wei(1, "ether"),
    ).transact({"from": deployer_account.address})
    testerchain.wait_for_receipt(tx)
    return alice


def test_coordinator_properties(agent):
    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == CoordinatorAgent.contract_name
    assert not agent._proxy_name  # not upgradeable


@pytest.mark.usefixtures("ursulas")
def test_initiate_ritual(
    agent,
    cohort,
    get_random_checksum_address,
    global_allow_list,
    transacting_powers,
    ritual_token,
    testerchain,
    initiator,
):
    number_of_rituals = agent.number_of_rituals()
    assert number_of_rituals == 0

    # TODO: Fixturize or read from contract
    fee_rate = 1
    duration = 60 * 60 * 24
    amount = len(cohort) * fee_rate * duration

    # Approve the ritual token for the coordinator agent to spend
    tx = ritual_token.functions.approve(agent.contract_address, amount).transact(
        {"from": initiator.transacting_power.account}
    )
    testerchain.wait_for_receipt(tx)

    authority = get_random_checksum_address()
    receipt = agent.initiate_ritual(
        providers=cohort,
        authority=authority,
        duration=duration,
        access_controller=global_allow_list.address,
        transacting_power=initiator.transacting_power,
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
        == agent.Ritual.Status.AWAITING_TRANSCRIPTS
    )

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert ritual_dkg_key is None  # no dkg key available until ritual is completed


def test_post_transcript(agent, transcripts, transacting_powers):
    ritual_id = agent.number_of_rituals() - 1
    for i, transacting_power in enumerate(transacting_powers):
        receipt = agent.post_transcript(
            ritual_id=ritual_id,
            transcript=transcripts[i],
            transacting_power=transacting_power,
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
        == agent.Ritual.Status.AWAITING_AGGREGATIONS
    )

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert ritual_dkg_key is None  # no dkg key available until ritual is completed


def test_post_aggregation(
    agent, aggregated_transcript, dkg_public_key, transacting_powers, cohort
):
    ritual_id = agent.number_of_rituals() - 1
    participant_public_keys = {}
    for i, transacting_power in enumerate(transacting_powers):
        participant_public_key = SessionStaticSecret.random().public_key()
        receipt = agent.post_aggregation(
            ritual_id=ritual_id,
            aggregated_transcript=aggregated_transcript,
            public_key=dkg_public_key,
            participant_public_key=participant_public_key,
            transacting_power=transacting_power,
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

    assert agent.get_ritual_status(ritual_id=ritual_id) == agent.Ritual.Status.FINALIZED

    ritual_dkg_key = agent.get_ritual_public_key(ritual_id=ritual_id)
    assert bytes(ritual_dkg_key) == bytes(dkg_public_key)
