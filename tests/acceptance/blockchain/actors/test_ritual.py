import pytest_twisted
from ferveo_py import combine_decryption_shares, decrypt_with_shared_secret, encrypt
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from tests.utils.ursula import start_pytest_ursula_services

DKG_SIZE = 4

@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(ursulas, agency, testerchain, test_registry, alice, control_time):

    EventScannerTask.INTERVAL = 10

    cohort = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))
    assert len(cohort) == DKG_SIZE
    coordinator_agent = ContractAgency.get_agent(CoordinatorAgent, registry=test_registry)
    node = cohort[0]

    # Round 0 - Initiate the ritual
    def initialize(r):
        print("==================== INITIALIZING ====================")
        nodes = list(u.checksum_address for u in cohort)
        receipt = coordinator_agent.initiate_ritual(nodes=nodes, transacting_power=alice.transacting_power)
        return receipt

    # Round 0 - Initiate the ritual
    def check_initialize(receipt):
        print("==================== CHECKING INITIALIZATION ====================")
        testerchain.wait_for_receipt(receipt['transactionHash'])
        assert coordinator_agent.number_of_rituals() == 1
        node.ritual_tracker.refresh(fetch_rituals=[0])
        assert len(node.ritual_tracker.rituals) == 1
        assert coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS

    def check_finality(_):
        print("==================== CHECKING FINALITY ====================")
        assert node.coordinator_agent.get_ritual_status(0) == coordinator_agent.Ritual.Status.FINALIZED
        for ursula in cohort:
            assert ursula.get_transcript(0) is not None

    def test_encrypt_decrypt(_):
        print("==================== ENCRYPTING/DECRYPTING ====================")

        # side channel fakeout
        last_node = cohort[-1]
        encrypting_key = last_node.dkg_storage["public_keys"][0]
        generator = last_node.dkg_storage["generator_inverses"][0]
        # alternatively, we could derive the key from the transcripts

        # In the meantime, the client creates a ciphertext and decryption request
        plaintext = "abc".encode()
        conditions = "my-aad".encode()
        ciphertext = encrypt(plaintext, conditions, encrypting_key)

        # Having aggregated the transcripts, the validators can now create decryption shares
        # this is normally done by the network client, but we'll do it here for simplicity
        decryption_shares = list()
        for ursula in cohort:
            # TODO: This is a hack to get the decryption share.  We should have a method on Ursula's API
            share = ursula.derive_decryption_share(ritual_id=0, ciphertext=ciphertext, conditions=conditions)
            decryption_shares.append(share)

        # Now, the decryption share can be used to decrypt the ciphertext
        shared_secret = combine_decryption_shares(decryption_shares)
        cleartext = decrypt_with_shared_secret(ciphertext, conditions, shared_secret, generator)
        assert bytes(cleartext) == plaintext
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!1")

    def block_until_dkg_finalized(d):
        while node.coordinator_agent.get_ritual_status(0) != coordinator_agent.Ritual.Status.FINALIZED:
            # simulates the passage of time and the execution of the event scanner
            for ursula in cohort:
                ursula.ritual_tracker.scan()
                ursula.ritual_tracker.refresh()

    def start_ursulas():
        for ursula in cohort:
            ursula.ritual_tracker.start()
            ursula.start_learning_loop(now=True)
            start_pytest_ursula_services(ursula=ursula)

    def stop(r):
        for ursula in cohort:
            ursula.ritual_tracker.stop()
            ursula.start_learning_loop()

    # setup
    d = deferToThread(start_ursulas)

    # initiate the ritual
    d.addCallback(initialize)
    d.addCallback(check_initialize)

    # wait for the dkg to finalize
    d.addCallback(block_until_dkg_finalized)
    d.addCallback(check_finality)

    # test encryption/decryption
    d.addCallback(test_encrypt_decrypt)

    # tear down
    d.addCallback(stop)

    yield d
