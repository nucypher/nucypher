import pytest
import pytest_twisted

from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.characters.lawful import Ursula
from nucypher.network.signing import (
    EIP191SignatureRequest,
    UserOperationSignatureRequest,
)
from nucypher.policy.conditions.auth.evm import EIP1271Auth
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.erc4337_utils import (
    AAVersion,
    create_erc20_transfer,
    create_eth_transfer,
)


@pytest.fixture(scope="module")
def cohort_id():
    return 0


@pytest.fixture(scope="module")
def dkg_size():
    return 4


@pytest.fixture(scope="module")
def duration():
    return 48 * 60 * 60


@pytest.fixture(scope="module")
def interval(testerchain):
    return testerchain.tx_machine._task.interval


@pytest.fixture(scope="module", autouse=True)
def transaction_tracker(testerchain, signing_coordinator_agent):
    testerchain.tx_machine.w3 = signing_coordinator_agent.blockchain.w3
    testerchain.tx_machine.start()


@pytest.fixture(scope="module")
def cohort(testerchain, clock, signing_coordinator_agent, ursulas, dkg_size):
    nodes = list(sorted(ursulas[:dkg_size], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == dkg_size
    for node in nodes:
        node.signing_ritual_tracker.task._task.clock = clock
        node.signing_ritual_tracker.start()
    return nodes


# TODO figure out why I can't do this in conftest.py
@pytest.fixture(scope="module")
def ritual_initiator(initiator, signing_coordinator, deployer_account):
    signing_coordinator.grantRole(
        signing_coordinator.INITIATOR_ROLE(),
        initiator.transacting_power.account,
        sender=deployer_account,
    )
    return initiator


def get_cohort_multisig(cohort_id, nucypher_dependency, signing_coordinator_child):
    threshold_signing_multisig_clone_factory = (
        nucypher_dependency.ThresholdSigningMultisigCloneFactory.at(
            signing_coordinator_child.signingMultisigFactory()
        )
    )
    multisig_address = threshold_signing_multisig_clone_factory.getCloneAddress(
        cohort_id
    )
    multisig = nucypher_dependency.ThresholdSigningMultisig.at(multisig_address)
    return multisig


def test_signing_cohort_initiation(
    chain,
    signing_coordinator_agent,
    accounts,
    ritual_initiator,
    cohort,
    testerchain,
    cohort_id,
    duration,
):
    print("==================== INITIALIZING ====================")
    cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)

    receipt = signing_coordinator_agent.initiate_signing_cohort(
        chain_id=chain.chain_id,
        authority=ritual_initiator.transacting_power.account,
        providers=cohort_staking_provider_addresses,
        threshold=len(cohort_staking_provider_addresses) - 1,
        duration=duration,
        transacting_power=ritual_initiator.transacting_power,
    )

    testerchain.time_travel(seconds=1)
    testerchain.wait_for_receipt(receipt["transactionHash"])

    # check that the ritual was created on-chain
    assert signing_coordinator_agent.number_of_cohorts() == cohort_id + 1
    assert (
        signing_coordinator_agent.get_signing_cohort_status(cohort_id)
        == SigningCoordinator.RitualStatus.AWAITING_SIGNATURES
    )


@pytest_twisted.inlineCallbacks
def test_signing_cohort_finality(
    signing_coordinator_agent,
    cohort_id,
    cohort,
    clock,
    interval,
    testerchain,
    ritual_initiator,
):
    print("==================== AWAITING COHORT FINALITY ====================")
    while (
        signing_coordinator_agent.get_signing_cohort_status(cohort_id)
        != SigningCoordinator.RitualStatus.ACTIVE
    ):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running

    assert signing_coordinator_agent.is_cohort_active(cohort_id)
    yield


def test_signature_publication(signing_coordinator_agent, cohort, cohort_id, dkg_size):
    print("==================== VERIFYING DKG FINALITY ====================")
    for ursula in cohort:
        assert (
            len(
                signing_coordinator_agent.get_signer(
                    cohort_id=cohort_id,
                    provider=ursula.checksum_address,
                ).signature
            )
            > 0
        ), "no signature found for ursula"

    assert len(signing_coordinator_agent.get_signing_cohort(cohort_id).conditions) > 0


def test_get_signers(
    nucypher_dependency,
    signing_coordinator_agent,
    cohort,
    cohort_id,
    dkg_size,
    signing_coordinator_child,
):
    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)
    for i, signer in enumerate(signing_cohort.signers):
        assert signer.provider == cohort[i].checksum_address
        assert signer.signature

    assert len(signing_cohort.signers) == dkg_size

    # check deployed multisig
    cohort_multisig = get_cohort_multisig(
        cohort_id, nucypher_dependency, signing_coordinator_child
    )
    operator_addresses = [u.operator_address for u in cohort]

    assert cohort_multisig.getSigners() == operator_addresses
    assert cohort_multisig.threshold() == len(cohort) - 1
    assert cohort_multisig.owner() == signing_coordinator_child.address


@pytest_twisted.inlineCallbacks
def test_signing_request_fulfilment(
    chain,
    bob,
    accounts,
    signing_coordinator_agent,
    signing_coordinator_child,
    initiator,
    cohort_id,
    cohort,
    nucypher_dependency,
    ritual_initiator,
    time_condition,
):
    bob.start_learning_loop(now=True)

    signing_request = EIP191SignatureRequest(
        data=b"Test data for signing",
        cohort_id=cohort_id,
        chain_id=chain.chain_id,
        context=None,
    )

    print("============= SIGNING REQUEST (NO CONDITION)==============")
    with pytest.raises(Ursula.NotEnoughUrsulas, match="Condition not configured"):
        _ = yield bob.request_threshold_signatures(
            signing_request=signing_request,
        )
    print("===================== SIGNING FAILED =====================")

    print("==================== TEST EIP-191 SIGNING REQUEST ====================")
    # set condition for cohort and chain
    on_chain_condition_lingo = ConditionLingo(time_condition)
    signing_coordinator_agent.set_signing_cohort_conditions(
        cohort_id,
        chain.chain_id,
        on_chain_condition_lingo,
        ritual_initiator.transacting_power,
    )

    responses = yield bob.request_threshold_signatures(
        signing_request=signing_request,
    )

    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)
    assert len(responses) >= signing_cohort.threshold

    multisig = get_cohort_multisig(
        cohort_id, nucypher_dependency, signing_coordinator_child
    )

    message_hash = None
    aggregated_signature = b""
    for r in responses:
        if message_hash is None:
            message_hash = r.hash
        assert message_hash == r.hash, "All hashes must be the same"
        aggregated_signature += r.signature

    result = multisig.isValidSignature(message_hash, aggregated_signature)

    assert (
        result == EIP1271Auth.MAGIC_VALUE_BYTES
    ), f"Invalid signature: {result} != {EIP1271Auth.MAGIC_VALUE_BYTES}"
    print("===================== SIGNING SUCCESSFUL =====================")
    yield


@pytest_twisted.inlineCallbacks
@pytest.mark.parametrize("aa_version", [AAVersion.V08, AAVersion.MDT])
def test_user_op_signing_request_fulfilment(
    aa_version,
    chain,
    bob,
    accounts,
    signing_coordinator_agent,
    signing_coordinator_child,
    initiator,
    cohort_id,
    cohort,
    nucypher_dependency,
    ritual_initiator,
):
    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)

    print("==================== TESTING USER OPERATION SIGNING ====================")

    # Test create_eth_transfer helper
    eth_transfer_op = create_eth_transfer(
        sender=accounts[0].address,
        nonce=1,
        to=accounts[1].address,
        value=1000000000000000000,  # 1 ETH in wei
        verification_gas_limit=100000,
        call_gas_limit=100000,
        pre_verification_gas=21000,
        max_priority_fee_per_gas=1000000000,
        max_fee_per_gas=2000000000,
        # no paymaster data
    )

    # Test that the ETH transfer operation was created correctly
    assert eth_transfer_op.sender == accounts[0].address
    assert eth_transfer_op.nonce == 1
    assert len(eth_transfer_op.call_data) > 0  # Should have encoded call data

    # Test signing the ETH transfer operation
    eth_signing_request = UserOperationSignatureRequest(
        user_op=eth_transfer_op,
        aa_version=aa_version,
        chain_id=chain.chain_id,
        cohort_id=cohort_id,
        context=None,
    )
    responses = yield bob.request_threshold_signatures(
        signing_request=eth_signing_request,
    )

    # Verify ETH transfer signatures
    assert len(responses) >= signing_cohort.threshold
    message_hash = None
    aggregated_signature = b""
    for r in responses:
        if message_hash is None:
            message_hash = r.hash
        assert message_hash == r.hash, "All hashes must be the same"
        aggregated_signature += r.signature

    multisig = get_cohort_multisig(
        cohort_id, nucypher_dependency, signing_coordinator_child
    )
    eth_result = multisig.isValidSignature(message_hash, aggregated_signature)
    assert (
        eth_result == EIP1271Auth.MAGIC_VALUE_BYTES
    ), f"Invalid ETH transfer signature: {eth_result} != {EIP1271Auth.MAGIC_VALUE_BYTES}"
    print("ETH transfer signing successful")

    # Test create_erc20_transfer helper
    # Using a mock ERC20 token address
    mock_token_address = "0x1234567890123456789012345678901234567890"
    erc20_transfer_op = create_erc20_transfer(
        sender=accounts[0].address,
        nonce=2,
        token=mock_token_address,
        to=accounts[1].address,
        amount=1000000000000000000,  # 1 token (assuming 18 decimals)
        verification_gas_limit=100000,
        call_gas_limit=100000,
        pre_verification_gas=21000,
        max_priority_fee_per_gas=1000000000,
        max_fee_per_gas=2000000000,
        # paymaster data
        paymaster=accounts[1].address,
        paymaster_post_op_gas_limit=100000,
        paymaster_verification_gas_limit=200000,
        paymaster_data=b"",
    )

    # Test that the ERC20 transfer operation was created correctly
    assert erc20_transfer_op.sender == accounts[0].address
    assert erc20_transfer_op.nonce == 2
    assert len(erc20_transfer_op.call_data) > 0  # Should have encoded call data

    # Test signing the ERC20 transfer operation
    erc20_signing_request = UserOperationSignatureRequest(
        user_op=erc20_transfer_op,
        aa_version=aa_version,
        chain_id=chain.chain_id,
        cohort_id=cohort_id,
        context=None,
    )
    responses = yield bob.request_threshold_signatures(
        signing_request=erc20_signing_request,
    )

    # Verify ERC20 transfer signatures
    assert len(responses) >= signing_cohort.threshold
    message_hash = None
    aggregated_signature = b""
    for r in responses:
        if message_hash is None:
            message_hash = r.hash
        assert message_hash == r.hash, "All hashes must be the same"
        aggregated_signature += r.signature

    erc20_result = multisig.isValidSignature(message_hash, aggregated_signature)
    assert (
        erc20_result == EIP1271Auth.MAGIC_VALUE_BYTES
    ), f"Invalid ERC20 transfer signature: {erc20_result} != {EIP1271Auth.MAGIC_VALUE_BYTES}"
    print("ERC20 transfer signing successful")
    print("===================== SIGNING SUCCESSFUL =====================")

    yield
