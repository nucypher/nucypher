import pytest
import pytest_twisted
from time import time
from twisted.internet.threads import deferToThread
from typing import List
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.characters.lawful import Enrico, Ursula
from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"
CONDITIONS = [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]

# TODO: GEt these from the contract
ROUND_1_EVENT_NAME = 'StartTranscriptRound'
ROUND_2_EVENT_NAME = 'StartAggregationRound'

PARAMS = [  # dkg_size, ritual_id, variant

    (1, 0, 'simple'),
    (4, 1, 'simple'),
    (8, 2, 'simple'),
    # TODO: enable these tests
    # (32, 3, 'simple'),

    # TODO: enable these tests
    # (1, 3, 'precomputed'),
    # (4, 5, 'precomputed'),
    # (8, 6, 'precomputed'),
    # (32, 7, 'precomputed'),

]

BLOCKS = list(reversed(range(1, 100)))
COORDINATOR = MockCoordinatorAgent(MockBlockchain())


@pytest.fixture(scope="function", autouse=True)
def mock_coordinator_agent(testerchain, application_economics, mock_contract_agency):
    mock_contract_agency._MockContractAgency__agents[CoordinatorAgent] = COORDINATOR
    yield COORDINATOR


@pytest.fixture(scope='function')
def cohort(ursulas, mock_coordinator_agent):
    """Creates a cohort of Ursulas"""
    for u in ursulas:
        u.coordinator_agent = mock_coordinator_agent
        u.ritual_tracker.coordinator_agent = mock_coordinator_agent
    return ursulas


def execute_round(cohort: List[Ursula], ritual_id: int, event_name: str):

    # check that the ritual is being tracked locally upon initialization for each node
    for ursula in cohort:
        # this is a testing hack to make the event scanner work
        # normally it's called by the reactor clock in a loop
        event = AttributeDict(dict(
            timestamp=lambda: int(time()),
            event=event_name,
            blockNumber=BLOCKS.pop(),
            args=AttributeDict({'ritualId': ritual_id})
        ))

        ursula.ritual_tracker._handle_ritual_event(event, get_block_when=lambda x: event)


@pytest.mark.parametrize('dkg_size, ritual_id, variant', PARAMS)
@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(testerchain, mock_coordinator_agent, cohort, alice, bob, dkg_size, ritual_id, variant):
    """Tests the DKG and the encryption/decryption of a message"""

    cohort = cohort[:dkg_size]

    def initialize():
        """Initiates the ritual"""
        print("==================== INITIALIZING ====================")
        cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)
        mock_coordinator_agent.initiate_ritual(
            nodes=cohort_staking_provider_addresses,
            transacting_power=alice.transacting_power
        )
        assert mock_coordinator_agent.number_of_rituals() == ritual_id + 1

    def round_1(_):
        """Checks the initialization of the ritual"""
        print("==================== CHECKING INITIALIZATION ====================")
        # verify that the ritual is in the correct state
        assert mock_coordinator_agent.get_ritual_status(ritual_id=ritual_id) == \
               mock_coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS
        execute_round(cohort, ritual_id, ROUND_1_EVENT_NAME)

    def round_2(_):
        """simulates the passage of time and the execution of the event scanner"""
        print("==================== BLOCKING UNTIL DKG FINALIZED ====================")
        execute_round(cohort, ritual_id, ROUND_2_EVENT_NAME)

    def finality(_):
        """Checks the finality of the DKG"""
        print("==================== CHECKING DKG FINALITY ====================")

        status = mock_coordinator_agent.get_ritual_status(ritual_id)
        assert status == mock_coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.dkg_storage.get_transcript(ritual_id) is not None

    def encrypt(_):
        """Encrypts a message and returns the ciphertext and conditions"""
        print("==================== DKG ENCRYPTION ====================")

        # side channel fake-out by using the datastore from the last node in the cohort
        # alternatively, we could use the coordinator datastore
        last_node = cohort[-1]
        encrypting_key = last_node.dkg_storage.get_public_key(ritual_id)

        # prepare message and conditions
        plaintext = PLAINTEXT.encode()

        # encrypt
        # print(f'encrypting for DKG with key {bytes(encrypting_key.to_bytes()).hex()}')
        enrico = Enrico(encrypting_key=encrypting_key)
        ciphertext = enrico.encrypt_for_dkg(plaintext=plaintext, conditions=CONDITIONS)
        return ciphertext

    def decrypt(ciphertext):
        """Decrypts a message and checks that it matches the original plaintext"""
        print("==================== DKG DECRYPTION ====================")
        bob.start_learning_loop(now=True)

        # ritual_id, ciphertext, conditions, and params are obtained from the side channel
        params = cohort[0].dkg_storage.get_dkg_params(ritual_id)

        cleartext = bob.threshold_decrypt(
            ritual_id=ritual_id,
            ciphertext=ciphertext,
            conditions=CONDITIONS,
            params=params,
            timeout=0,
            variant=variant
        )
        assert bytes(cleartext) == PLAINTEXT.encode()

        # again, but without `params`
        cleartext = bob.threshold_decrypt(
            ritual_id=ritual_id,
            ciphertext=ciphertext,
            conditions=CONDITIONS,
            timeout=0,
            variant=variant
        )
        assert bytes(cleartext) == PLAINTEXT.encode()
        print("==================== DECRYPTION SUCCESSFUL ====================")

    def error_handler(e):
        """Prints the error and raises it"""
        print("==================== ERROR ====================")
        print(e.getTraceback())
        raise e

    # order matters
    d = deferToThread(initialize)
    callbacks = [
        round_1,
        round_2,
        finality,
        encrypt,
        decrypt,
    ]
    for callback in callbacks:
        d.addCallback(callback)
        d.addErrback(error_handler)
    yield d
