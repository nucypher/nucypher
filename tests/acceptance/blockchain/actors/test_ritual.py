import json

import pytest_twisted
from ferveo_py import combine_decryption_shares, decrypt_with_shared_secret, encrypt, DecryptionShare
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from nucypher.characters.lawful import Enrico
from nucypher.utilities.mock import ThresholdDecryptionRequest
from nucypher_core import Conditions
from tests.utils.ursula import start_pytest_ursula_services

DKG_SIZE = 4

@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, agency, testerchain, test_registry, alice, bob, control_time):

    EventScannerTask.INTERVAL = 1
    cohort = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))
    assert len(cohort) == DKG_SIZE
    coordinator_agent = ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)
    node = cohort[0]

    def start_ursulas():
        for ursula in cohort:
            ursula.ritual_tracker.start()
            ursula.start_learning_loop(now=True)
            start_pytest_ursula_services(ursula=ursula)

    # Round 0 - Initiate the ritual
    def initialize(r):
        print("==================== INITIALIZING ====================")
        nodes = list(u.checksum_address for u in cohort)
        receipt = coordinator_agent.initiate_ritual(nodes=nodes, transacting_power=alice.transacting_power)
        return receipt

    # Round 0 - Initiate the ritual
    def test_initialize(receipt):
        print("==================== CHECKING INITIALIZATION ====================")
        testerchain.wait_for_receipt(receipt['transactionHash'])
        assert coordinator_agent.number_of_rituals() == 1
        node.ritual_tracker.refresh(fetch_rituals=[0])
        assert len(node.ritual_tracker.rituals) == 1
        assert coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS

    def block_until_dkg_finalized(d):
        # simulates the passage of time and the execution of the event scanner
        print("==================== BLOCKING UNTIL DKG FINALIZED ====================")
        while node.coordinator_agent.get_ritual_status(0) != coordinator_agent.Ritual.Status.FINALIZED:
            for ursula in cohort:
                ursula.ritual_tracker.task.run()
            testerchain.time_travel(seconds=60)

    def test_finality(_):
        print("==================== CHECKING DKG FINALITY ====================")
        assert node.coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.get_transcript(0) is not None

    def test_encrypt(_):
        print("==================== DKG ENCRYPTION ====================")

        # side channel fakeout
        last_node = cohort[-1]
        encrypting_key = last_node.dkg_storage["public_keys"][0]

        # prepare message and conditions
        plaintext = "peace at dawn".encode()
        conditions = [{'returnValueTest': {'value': '0', 'comparator': '>'}, 'method': 'timelock'}]

        # encrypt
        enrico = Enrico(encrypting_key=encrypting_key)
        ciphertext, signature = enrico.encrypt_for_dkg(plaintext=plaintext, conditions=conditions)
        return ciphertext, conditions

    def test_decrypt(r):
        print("==================== DKG DECRYPTION ====================")
        ciphertext, conditions = r  # unpack the result of test_encrypt_decrypt

        # side channel fakeout
        last_node = cohort[-1]
        generator = last_node.dkg_storage["generator_inverses"][0]

        # decrypt
        cleartext = bob.threshold_decrypt(
            ritual_id=0,
            ciphertext=ciphertext,
            conditions=conditions,
            generator=generator,
            cohort=cohort
        )
        assert bytes(cleartext) == "peace at dawn".encode()

    def stop(*args):
        print("==================== STOPPING ====================")
        print(args)
        for ursula in cohort:
            ursula.ritual_tracker.stop()
            ursula.start_learning_loop()

    callbacks = [
        initialize,
        test_initialize,
        block_until_dkg_finalized,
        test_finality,
        test_encrypt,
        test_decrypt,
        stop
    ]

    error_handler = lambda e: print(e.getTraceback() )
    d = deferToThread(start_ursulas)
    for callback in callbacks:
        d.addCallback(callback)
        d.addErrback(error_handler)
    yield d
