import pytest
import pytest_twisted
from twisted.internet.threads import deferToThread
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from nucypher.characters.lawful import Enrico

# constants
DKG_SIZE = 1
RITUAL_ID = 0

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"
CONDITIONS = [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]


@pytest.fixture(scope='function')
def cohort(ursulas, mock_coordinator_agent):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == DKG_SIZE  # sanity check
    for u in ursulas:
        u.coordinator_agent = mock_coordinator_agent
        u.ritual_tracker.coordinator_agent = mock_coordinator_agent
    return nodes


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(testerchain, mock_coordinator_agent, cohort, alice, bob):
    """Tests the DKG and the encryption/decryption of a message"""

    # Round 0 - Initiate the ritual
    def initialize():
        """Initiates the ritual"""
        print("==================== INITIALIZING ====================")
        cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)
        receipt = mock_coordinator_agent.initiate_ritual(
            nodes=cohort_staking_provider_addresses,
            transacting_power=alice.transacting_power
        )
        return receipt

    # Round 0 - Initiate the ritual
    def test_initialize(receipt):
        """Checks the initialization of the ritual"""
        print("==================== CHECKING INITIALIZATION ====================")

        # check that the ritual was created on-chain
        assert mock_coordinator_agent.number_of_rituals() == RITUAL_ID + 1
        assert mock_coordinator_agent.get_ritual_status(RITUAL_ID) == mock_coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS

        # check that the ritual is being tracked locally upon initialization for each node
        for ursula in cohort:
            # this is a testing hack to make the event scanner work
            # normally it's called by the reactor clock in a loop
            event = AttributeDict(dict(
                timestamp=lambda: 123456789,
                event='StartTranscriptRound',
                blockNumber=0,
                args=AttributeDict({'ritualId': RITUAL_ID})
            ))

            d = ursula.ritual_tracker._handle_ritual_event(event, get_block_when=lambda x: event)
            # check that the ritual was created locally for this node
            assert len(ursula.ritual_tracker.rituals) == RITUAL_ID + 1

    def block_until_dkg_finalized(_):
        """simulates the passage of time and the execution of the event scanner"""
        print("==================== BLOCKING UNTIL DKG FINALIZED ====================")
        for ursula in cohort:
            # this is a testing hack to make the event scanner work
            # normally it's called by the reactor clock in a loop
            event = AttributeDict(dict(
                timestamp=lambda: 123456789,
                event='StartAggregationRound',
                blockNumber=0,
                args=AttributeDict({'ritualId': RITUAL_ID})
            ))
            ursula.ritual_tracker._handle_ritual_event(event, get_block_when=lambda x: event)
            # check that the ritual was created locally for this node
            assert len(ursula.ritual_tracker.rituals) == RITUAL_ID + 1

    def test_finality(_):
        """Checks the finality of the DKG"""
        print("==================== CHECKING DKG FINALITY ====================")

        status = mock_coordinator_agent.get_ritual_status(RITUAL_ID)
        assert status == mock_coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.dkg_storage.get_transcript(RITUAL_ID) is not None

    def test_encrypt(_):
        """Encrypts a message and returns the ciphertext and conditions"""
        print("==================== DKG ENCRYPTION ====================")

        # side channel fake-out by using the datastore from the last node in the cohort
        # alternatively, we could use the coordinator datastore
        last_node = cohort[-1]
        encrypting_key = last_node.dkg_storage.get_public_key(RITUAL_ID)

        # prepare message and conditions
        plaintext = PLAINTEXT.encode()

        # encrypt
        # print(f'encrypting for DKG with key {bytes(encrypting_key.to_bytes()).hex()}')
        enrico = Enrico(encrypting_key=encrypting_key)
        ciphertext = enrico.encrypt_for_dkg(plaintext=plaintext, conditions=CONDITIONS)
        return ciphertext

    def test_decrypt(ciphertext):
        """Decrypts a message and checks that it matches the original plaintext"""
        print("==================== DKG DECRYPTION ====================")
        # ritual_id, ciphertext, conditions are obtained from the side channel
        bob.start_learning_loop(now=True)
        cleartext = bob.threshold_decrypt(
            ritual_id=RITUAL_ID,
            ciphertext=ciphertext,
            conditions=CONDITIONS,
            # params=cohort[0].dkg_storage.get_dkg_params(RITUAL_ID),
        )
        assert bytes(cleartext) == PLAINTEXT.encode()
        print("==================== DECRYPTION SUCCESSFUL ====================")

    def error_handler(e):
        """Prints the error and raises it"""
        print("==================== ERROR ====================")
        print(e.getTraceback())
        raise e

    # order matters
    callbacks = [
        test_initialize,
        block_until_dkg_finalized,
        test_finality,
        test_encrypt,
        test_decrypt,
    ]

    d = deferToThread(initialize)
    for callback in callbacks:
        d.addCallback(callback)
        d.addErrback(error_handler)
    yield d
