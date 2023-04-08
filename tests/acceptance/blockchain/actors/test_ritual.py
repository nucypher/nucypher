import pytest
import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from nucypher.characters.lawful import Enrico
from tests.utils.ursula import start_pytest_ursula_services

# constants
DKG_SIZE = 4
RITUAL_ID = 0

# This is a hack to make the tests run faster
EventScannerTask.INTERVAL = 1
TIME_TRAVEL_INTERVAL = 60

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"
CONDITIONS = [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]


@pytest.fixture(scope='module')
def coordinator_agent(testerchain, test_registry):
    """Creates a coordinator agent"""
    return ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)


def sample_nodes_for_dkg(ursulas):
    """Selects a sample of nodes for the DKG"""
    return list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, coordinator_agent, testerchain, alice, bob):
    """Tests the DKG and the encryption/decryption of a message"""

    cohort = sample_nodes_for_dkg(ursulas)
    assert len(cohort) == DKG_SIZE  # sanity check

    def start_ursulas():
        """Starts the learning loop and the event scanner"""
        for ursula in cohort:
            ursula.ritual_tracker.start()
            ursula.start_learning_loop(now=True)
            start_pytest_ursula_services(ursula=ursula)

    # Round 0 - Initiate the ritual
    def initialize(_):
        """Initiates the ritual"""
        print("==================== INITIALIZING ====================")
        cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)
        receipt = coordinator_agent.initiate_ritual(
            nodes=cohort_staking_provider_addresses,
            transacting_power=alice.transacting_power
        )
        return receipt

    # Round 0 - Initiate the ritual
    def test_initialize(receipt):
        """Checks the initialization of the ritual"""
        print("==================== CHECKING INITIALIZATION ====================")
        testerchain.wait_for_receipt(receipt['transactionHash'])

        # check that the ritual was created on-chain
        assert coordinator_agent.number_of_rituals() == RITUAL_ID + 1
        assert coordinator_agent.get_ritual_status(RITUAL_ID) == coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS

        # check that the ritual was created locally for each node
        for ursula in cohort:
            ursula.ritual_tracker.refresh(fetch_rituals=[RITUAL_ID])
            assert len(ursula.ritual_tracker.rituals) == RITUAL_ID + 1

    def block_until_dkg_finalized(_):
        """simulates the passage of time and the execution of the event scanner"""
        print("==================== BLOCKING UNTIL DKG FINALIZED ====================")
        while coordinator_agent.get_ritual_status(RITUAL_ID) != coordinator_agent.Ritual.Status.FINALIZED:
            for ursula in cohort:
                # this is a testing hack to make the event scanner work,
                # normally it's called by the reactor clock in a loop
                ursula.ritual_tracker.task.run()
            testerchain.time_travel(seconds=TIME_TRAVEL_INTERVAL)

    def test_finality(_):
        """Checks the finality of the DKG"""
        print("==================== CHECKING DKG FINALITY ====================")
        assert coordinator_agent.get_ritual_status(RITUAL_ID) == coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.get_transcript(RITUAL_ID) is not None

    def test_encrypt(_):
        """Encrypts a message and returns the ciphertext and conditions"""
        print("==================== DKG ENCRYPTION ====================")

        # side channel fake-out
        last_node = cohort[-1]
        encrypting_key = last_node.dkg_storage["public_keys"][RITUAL_ID]

        # prepare message and conditions
        plaintext = PLAINTEXT.encode()

        # encrypt
        enrico = Enrico(encrypting_key=encrypting_key)
        ciphertext = enrico.encrypt_for_dkg(plaintext=plaintext, conditions=CONDITIONS)
        return ciphertext

    def test_decrypt(ciphertext):
        """Decrypts a message and checks that it matches the original plaintext"""
        print("==================== DKG DECRYPTION ====================")

        # side channel fake-out
        last_node = cohort[-1]
        generator = last_node.dkg_storage["generator_inverses"][RITUAL_ID]

        # decrypt
        cleartext = bob.threshold_decrypt(
            ritual_id=RITUAL_ID,
            ciphertext=ciphertext,
            conditions=CONDITIONS,
            generator=generator,
            cohort=cohort
        )
        assert bytes(cleartext) == PLAINTEXT.encode()
        print("==================== DECRYPTION SUCCESSFUL ====================")

    def stop(*args):
        """Stops the learning loop and the event scanner"""
        print("==================== STOPPING ====================")
        for ursula in cohort:
            ursula.ritual_tracker.stop()
            ursula.start_learning_loop()

    def error_handler(e):
        """Prints the error and raises it"""
        print("==================== ERROR ====================")
        # print(e.getTraceback())
        raise e

    # order matters
    callbacks = [
        initialize,
        test_initialize,
        block_until_dkg_finalized,
        test_finality,
        test_encrypt,
        test_decrypt,
        stop
    ]

    d = deferToThread(start_ursulas)
    for callback in callbacks:
        d.addCallback(callback)
        d.addErrback(error_handler)
    yield d
