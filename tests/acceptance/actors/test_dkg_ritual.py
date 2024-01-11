import os
import random

import pytest
import pytest_twisted
from hexbytes import HexBytes
from prometheus_client import REGISTRY
from twisted.internet.threads import deferToThread

from nucypher.blockchain.eth.agents import ContractAgency, SubscriptionManagerAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.trackers.dkg import EventScannerTask
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    NotCompoundCondition,
    OrCompoundCondition,
    ReturnValueTest,
)
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TEST_ETH_PROVIDER_URI, TESTERCHAIN_CHAIN_ID
from tests.utils.blockchain import TestAccount

# constants
DKG_SIZE = 4
RITUAL_ID = 0

# This is a hack to make the tests run faster
EventScannerTask.INTERVAL = 1
TIME_TRAVEL_INTERVAL = 60

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"

DURATION = 48 * 60 * 60


@pytest.fixture(scope="module")
def condition(test_registry):
    time_condition = TimeCondition(
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator=">", value=0),
    )
    rpc_condition = RPCCondition(
        chain=TESTERCHAIN_CHAIN_ID,
        method="eth_getBalance",
        return_value_test=ReturnValueTest(comparator="==", value=0),
        parameters=["0x0000000000000000000000000000000000000007"],  # random account
    )

    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )
    contract_condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(
            comparator="==", value=[NULL_ADDRESS, 0, 0, 0, NULL_ADDRESS]
        ),
        parameters=[HexBytes(os.urandom(16)).hex()],
    )

    or_condition = OrCompoundCondition(
        operands=[time_condition, rpc_condition, contract_condition]
    )

    and_condition = OrCompoundCondition(
        operands=[time_condition, rpc_condition, contract_condition]
    )

    not_not_condition = NotCompoundCondition(
        operand=NotCompoundCondition(operand=and_condition)
    )

    conditions = [
        time_condition,
        rpc_condition,
        contract_condition,
        or_condition,
        and_condition,
        not_not_condition,
    ]

    condition_to_use = random.choice(conditions)
    return ConditionLingo(condition_to_use).to_dict()


@pytest.fixture(scope='module')
def cohort(ursulas):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:DKG_SIZE], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == DKG_SIZE  # sanity check
    return nodes


@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(
    bond_operators,
    condition,
    accounts,
    coordinator_agent,
    global_allow_list,
    cohort,
    initiator,
    bob,
    ritual_token,
    testerchain,
    test_registry,
):
    """Tests the DKG and the encryption/decryption of a message"""

    enrico_wallet = accounts.unassigned_wallets[0]

    # #TODO: This is a hack to handle two wallet types in the same test
    initiator_account = accounts.ape_accounts[1]
    initiator_wallet = TestAccount.from_key(initiator_account.private_key)

    # Round 0 - Initiate the ritual
    def initialize():
        """Initiates the ritual"""
        print("==================== INITIALIZING ====================")
        cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)

        # Approve the ritual token for the coordinator agent to spend
        amount = coordinator_agent.get_ritual_initiation_cost(
            providers=cohort_staking_provider_addresses, duration=DURATION
        )
        ritual_token.approve(
            coordinator_agent.contract_address,
            amount,
            sender=initiator_account,
        )

        receipt = coordinator_agent.initiate_ritual(
            providers=cohort_staking_provider_addresses,
            authority=initiator.wallet.address,
            duration=DURATION,
            access_controller=global_allow_list.address,
            wallet=initiator_wallet,
        )
        return receipt

    # Round 0 - Initiate the ritual
    def test_initialize(receipt):
        """Checks the initialization of the ritual"""
        print("==================== CHECKING INITIALIZATION ====================")
        testerchain.wait_for_receipt(receipt['transactionHash'])

        # check that the ritual was created on-chain
        assert coordinator_agent.number_of_rituals() == RITUAL_ID + 1
        assert (
            coordinator_agent.get_ritual_status(RITUAL_ID)
            == coordinator_agent.Ritual.Status.DKG_AWAITING_TRANSCRIPTS
        )

        # time travel has a side effect of mining a block so that the
        # scanner will definitively pick up ritual event
        testerchain.time_travel(seconds=1)

        for ursula in cohort:
            # this is a testing hack to make the event scanner work
            # normally it's called by the reactor clock in a loop
            ursula.ritual_tracker.task.run()
            # nodes received `StartRitual` and submitted their transcripts
            assert (
                len(
                    coordinator_agent.get_participant_from_provider(
                        ritual_id=RITUAL_ID, provider=ursula.checksum_address
                    ).transcript
                )
                > 0
            ), "ursula posted transcript to Coordinator"

    def block_until_dkg_finalized(_):
        """simulates the passage of time and the execution of the event scanner"""
        print("==================== BLOCKING UNTIL DKG FINALIZED ====================")
        while (
            coordinator_agent.get_ritual_status(RITUAL_ID)
            != coordinator_agent.Ritual.Status.ACTIVE
        ):
            for ursula in cohort:
                # this is a testing hack to make the event scanner work,
                # normally it's called by the reactor clock in a loop
                ursula.ritual_tracker.task.run()
            testerchain.time_travel(seconds=TIME_TRAVEL_INTERVAL)

        # Ensure that all events processed, including EndRitual
        for ursula in cohort:
            ursula.ritual_tracker.task.run()

    def test_finality(_):
        """Checks the finality of the DKG"""
        print("==================== CHECKING DKG FINALITY ====================")
        status = coordinator_agent.get_ritual_status(RITUAL_ID)
        assert status == coordinator_agent.Ritual.Status.ACTIVE
        for ursula in cohort:
            assert ursula.dkg_storage.get_transcript(RITUAL_ID) is not None

        last_scanned_block = REGISTRY.get_sample_value(
            "ritual_events_last_scanned_block_number"
        )
        assert last_scanned_block > 0

    def test_encrypt(_):
        """Encrypts a message and returns the ciphertext and conditions"""
        print("==================== DKG ENCRYPTION ====================")

        encrypting_key = coordinator_agent.get_ritual_public_key(ritual_id=RITUAL_ID)

        # prepare message and conditions
        plaintext = PLAINTEXT.encode()

        # create Enrico
        enrico = Enrico(encrypting_key=encrypting_key, wallet=enrico_wallet)

        # encrypt
        print(f"encrypting for DKG with key {bytes(encrypting_key).hex()}")
        threshold_message_kit = enrico.encrypt_for_dkg(
            plaintext=plaintext, conditions=condition
        )

        return threshold_message_kit

    def test_unauthorized_decrypt(threshold_message_kit):
        """Attempts to decrypt a message before Enrico is authorized to use the ritual"""
        print("======== DKG DECRYPTION UNAUTHORIZED ENCRYPTION ========")
        # ritual_id, ciphertext, conditions are obtained from the side channel
        bob.start_peering(now=True)
        with pytest.raises(
            Ursula.NotEnoughUrsulas,
            match=f"Encrypted data not authorized for ritual {RITUAL_ID}",
        ):
            _ = bob.threshold_decrypt(
                threshold_message_kit=threshold_message_kit,
            )

        # check prometheus metric for decryption requests
        # since all running on the same machine - the value is not per-ursula but rather all
        num_failures = REGISTRY.get_sample_value(
            "threshold_decryption_num_failures_total"
        )
        assert len(cohort) == int(num_failures)  # each ursula in cohort had a failure

        print("========= UNAUTHORIZED DECRYPTION UNSUCCESSFUL =========")

        return threshold_message_kit

    def test_decrypt(threshold_message_kit):
        """Decrypts a message and checks that it matches the original plaintext"""
        # authorize Enrico to encrypt for ritual
        global_allow_list.authorize(
            RITUAL_ID,
            [enrico_wallet.address],
            sender=initiator_account,
        )

        print("==================== DKG DECRYPTION ====================")
        # ritual_id, ciphertext, conditions are obtained from the side channel
        bob.start_peering(now=True)
        cleartext = bob.threshold_decrypt(
            threshold_message_kit=threshold_message_kit,
        )
        assert bytes(cleartext) == PLAINTEXT.encode()

        # check prometheus metric for decryption requests
        # since all running on the same machine - the value is not per-ursula but rather all
        num_successes = REGISTRY.get_sample_value(
            "threshold_decryption_num_successes_total"
        )

        ritual = coordinator_agent.get_ritual(RITUAL_ID)
        # at least a threshold of ursulas were successful (concurrency)
        assert int(num_successes) >= ritual.threshold
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
        test_unauthorized_decrypt,
        test_decrypt,
    ]

    d = deferToThread(initialize)
    for callback in callbacks:
        d.addCallback(callback)
        d.addErrback(error_handler)
    yield d

    # check prometheus metric for decryption requests
    # since all running on the same machine - the value is not per-ursula but rather all
    num_decryption_failures = REGISTRY.get_sample_value(
        "threshold_decryption_num_failures_total"
    )
    num_decryption_successes = REGISTRY.get_sample_value(
        "threshold_decryption_num_successes_total"
    )
    num_decryption_requests = REGISTRY.get_sample_value(
        "decryption_request_processing_count"
    )
    assert num_decryption_requests == (
        num_decryption_successes + num_decryption_failures
    )
