from time import time
from typing import List
from unittest.mock import PropertyMock, patch

import pytest
import pytest_twisted
from eth_typing import ChecksumAddress
from nucypher_core.ferveo import FerveoVariant
from twisted.internet.threads import deferToThread
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType
from tests.constants import TESTERCHAIN_CHAIN_ID
from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain

# The message to encrypt and its conditions
PLAINTEXT = "peace at dawn"
CONDITIONS = {
    "version": ConditionLingo.VERSION,
    "condition": {
        "conditionType": ConditionType.TIME.value,
        "returnValueTest": {"value": 0, "comparator": ">"},
        "method": "blocktime",
        "chain": TESTERCHAIN_CHAIN_ID,
    },
}


# TODO: Get these from the contract
ROUND_1_EVENT_NAME = "StartRitual"
ROUND_2_EVENT_NAME = "StartAggregationRound"

PARAMS = [  # dkg_size, ritual_id, variant
    (2, 0, FerveoVariant.Precomputed),
    (5, 1, FerveoVariant.Precomputed),
    (8, 2, FerveoVariant.Precomputed),
    (2, 3, FerveoVariant.Simple),
    (5, 4, FerveoVariant.Simple),
    (8, 5, FerveoVariant.Simple),
    # TODO: slow and need additional accounts for testing
    # (16, 6, FerveoVariant.Precomputed),
    # (16, 7, FerveoVariant.Simple),
    # (32, 8, FerveoVariant.Precomputed),
    # (32, 9, FerveoVariant.Simple),
]

BLOCKS = list(reversed(range(1, 1000)))
COORDINATOR = MockCoordinatorAgent(MockBlockchain())


@pytest.fixture(scope="function", autouse=True)
def mock_coordinator_agent(testerchain, mock_contract_agency):
    mock_contract_agency._MockContractAgency__agents[CoordinatorAgent] = COORDINATOR

    yield COORDINATOR
    COORDINATOR.reset()


@pytest.fixture(scope="function")
def cohort(ursulas, mock_coordinator_agent):
    """Creates a cohort of Ursulas"""
    for u in ursulas:
        # set mapping in coordinator agent
        mock_coordinator_agent._add_operator_to_staking_provider_mapping(
            {u.operator_address: u.checksum_address}
        )
        u.coordinator_agent = mock_coordinator_agent
        u.ritual_tracker.coordinator_agent = mock_coordinator_agent

    return ursulas


def execute_round_1(ritual_id: int, authority: ChecksumAddress, cohort: List[Ursula]):
    # check that the ritual is being tracked locally upon initialization for each node
    for ursula in cohort:
        # this is a testing hack to make the event scanner work
        # normally it's called by the reactor clock in a loop
        event = AttributeDict(
            dict(
                timestamp=lambda: int(time()),
                event=ROUND_1_EVENT_NAME,
                blockNumber=BLOCKS.pop(),
                args=AttributeDict(
                    {
                        "ritualId": ritual_id,
                        "authority": authority,
                        "participants": [u.checksum_address for u in cohort],
                    }
                ),
            )
        )

        ursula.ritual_tracker._handle_ritual_event(
            event, get_block_when=lambda x: event
        )


def execute_round_2(ritual_id: int, cohort: List[Ursula]):
    # check that the ritual is being tracked locally upon initialization for each node
    for ursula in cohort:
        # this is a testing hack to make the event scanner work
        # normally it's called by the reactor clock in a loop
        event = AttributeDict(
            dict(
                timestamp=lambda: int(time()),
                event=ROUND_2_EVENT_NAME,
                blockNumber=BLOCKS.pop(),
                args=AttributeDict({"ritualId": ritual_id}),
            )
        )

        ursula.ritual_tracker._handle_ritual_event(
            event, get_block_when=lambda x: event
        )


@pytest.mark.usefixtures("mock_sign_message")
@pytest.mark.parametrize("dkg_size, ritual_id, variant", PARAMS)
@pytest_twisted.inlineCallbacks()
def test_ursula_ritualist(
    testerchain,
    mock_coordinator_agent,
    cohort,
    alice,
    bob,
    dkg_size,
    ritual_id,
    variant,
    get_random_checksum_address,
):
    """Tests the DKG and the encryption/decryption of a message"""
    cohort = cohort[:dkg_size]

    # adjust threshold since we are testing with pre-computed (simple is the default)
    threshold = mock_coordinator_agent.get_threshold_for_ritual_size(
        dkg_size
    )  # default is simple
    if variant == FerveoVariant.Precomputed:
        threshold = dkg_size

    with patch.object(
        mock_coordinator_agent, "get_threshold_for_ritual_size", return_value=threshold
    ):

        def initialize():
            """Initiates the ritual"""
            print("==================== INITIALIZING ====================")
            cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)
            mock_coordinator_agent.initiate_ritual(
                providers=cohort_staking_provider_addresses,
                authority=alice.transacting_power.account,
                duration=1,
                access_controller=get_random_checksum_address(),
                transacting_power=alice.transacting_power,
            )
            assert mock_coordinator_agent.number_of_rituals() == ritual_id + 1

        def round_1(_):
            """Checks the initialization of the ritual"""
            print("==================== CHECKING INITIALIZATION ====================")
            # verify that the ritual is in the correct state
            assert (
                mock_coordinator_agent.get_ritual_status(ritual_id=ritual_id)
                == mock_coordinator_agent.Ritual.Status.AWAITING_TRANSCRIPTS
            )

            ritual = mock_coordinator_agent.get_ritual(ritual_id)
            execute_round_1(ritual_id, ritual.authority, cohort)

        def round_2(_):
            """simulates the passage of time and the execution of the event scanner"""
            print(
                "==================== BLOCKING UNTIL DKG FINALIZED ===================="
            )
            execute_round_2(ritual_id, cohort)

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
            encrypting_key = mock_coordinator_agent.get_ritual_public_key(
                ritual_id=ritual_id
            )

            # prepare message and conditions
            plaintext = PLAINTEXT.encode()

            # create Enrico
            signer = Web3Signer(client=testerchain.client)
            enrico = Enrico(encrypting_key=encrypting_key, signer=signer)

            # encrypt
            print(f"encrypting for DKG with key {bytes(encrypting_key).hex()}")
            threshold_message_kit = enrico.encrypt_for_dkg(
                plaintext=plaintext, conditions=CONDITIONS
            )
            return threshold_message_kit

        def decrypt_failure_cases(threshold_message_kit):
            # define failure test cases
            def unauthorized_encryptor():
                print("======== DKG DECRYPTION UNAUTHORIZED ENCRYPTION ========")
                with patch.object(
                    mock_coordinator_agent,
                    "is_encryption_authorized",
                    return_value=False,
                ):
                    with pytest.raises(
                        Ursula.NotEnoughUrsulas,
                        match=f"Encrypted data not authorized for ritual {ritual_id}",
                    ):
                        bob.threshold_decrypt(
                            threshold_message_kit=threshold_message_kit,
                            peering_timeout=0,
                        )
                print("========= UNAUTHORIZED DECRYPTION UNSUCCESSFUL =========")

            def expired_ritual():
                print("============ DKG DECRYPTION EXPIRED RITUAL =============")
                ritual = mock_coordinator_agent.get_ritual(ritual_id)
                time_in_past = mock_coordinator_agent.blockchain.get_blocktime() - 1
                with patch.object(ritual, "end_timestamp", time_in_past):
                    with pytest.raises(
                        Ursula.NotEnoughUrsulas, match=f"Ritual {ritual_id} is expired"
                    ):
                        bob.threshold_decrypt(
                            threshold_message_kit=threshold_message_kit,
                            peering_timeout=0,
                        )
                print("======== EXPIRED RITUAL DECRYPTION UNSUCCESSFUL ========")

            # run failure test cases
            bob.start_learning_loop(now=True)
            # mock the use of non-default variants since it can no longer be specified
            with patch.object(
                bob,
                "_default_dkg_variant",
                new_callable=PropertyMock(return_value=variant),
            ):
                unauthorized_encryptor()
                expired_ritual()

            return threshold_message_kit

        def decrypt(threshold_message_kit):
            """Decrypts a message and checks that it matches the original plaintext"""
            print("==================== DKG DECRYPTION ====================")
            bob.start_learning_loop(now=True)

            # mock the use of non-default variants since it can no longer be specified
            with patch.object(
                bob,
                "_default_dkg_variant",
                new_callable=PropertyMock(return_value=variant),
            ):
                cleartext = bob.threshold_decrypt(
                    threshold_message_kit=threshold_message_kit,
                    peering_timeout=0,
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
            decrypt_failure_cases,
            decrypt,
        ]
        for callback in callbacks:
            d.addCallback(callback)
            d.addErrback(error_handler)
        yield d
