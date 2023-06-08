import pytest
import pytest_twisted
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from nucypher.characters.lawful import Enrico
from tests.constants import TESTERCHAIN_CHAIN_ID

# constants
DKG_SIZE = 4
RITUAL_ID = 0

# This is a hack to make the tests run faster
EventScannerTask.INTERVAL = 1
TIME_TRAVEL_INTERVAL = 60

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"
CONDITIONS = [
    {
        "returnValueTest": {"value": "0", "comparator": ">"},
        "method": "blocktime",
        "chain": TESTERCHAIN_CHAIN_ID,
    }
]


@pytest.fixture(scope='module')
def cohort(ursulas):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == DKG_SIZE  # sanity check
    return nodes


@pytest.fixture(scope='module')
def coordinator_agent(testerchain, test_registry):
    """Creates a coordinator agent"""
    return ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(testerchain, coordinator_agent, cohort, alice, bob):
    """Tests the DKG and the encryption/decryption of a message"""

    # Round 0 - Initiate the ritual
    def initialize():
        """Initiates the ritual"""
        print("==================== INITIALIZING ====================")
        cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)
        receipt = coordinator_agent.initiate_ritual(
            providers=cohort_staking_provider_addresses,
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

        # time travel has a side effect of mining a block so that the scanner will definitively
        # pick up ritual event
        # TODO is there a better strategy
        testerchain.time_travel(seconds=1)

        # check that the ritual is being tracked locally upon initialization for each node
        for ursula in cohort:
            # this is a testing hack to make the event scanner work
            # normally it's called by the reactor clock in a loop
            ursula.ritual_tracker.task.run()
            # check that the ritual was created locally for this node
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
        status = coordinator_agent.get_ritual_status(RITUAL_ID)
        assert status == coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.dkg_storage.get_transcript(RITUAL_ID) is not None

    def test_encrypt(_):
        """Encrypts a message and returns the ciphertext and conditions"""
        print("==================== DKG ENCRYPTION ====================")

        encrypting_key = coordinator_agent.get_ritual_public_key(ritual_id=RITUAL_ID)

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
            peering_timeout=0
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
