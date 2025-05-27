import pytest
import pytest_twisted
from eth_account.messages import encode_typed_data
from hexbytes import HexBytes

from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.characters.lawful import Ursula
from nucypher.network.signing import SignatureRequest, SignatureType
from nucypher.policy.conditions.auth.evm import EIP1271Auth
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.utilities.erc4337_utils import PackedUserOperation


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
    threshold_signing_multisig_clone_factory = (
        nucypher_dependency.ThresholdSigningMultisigCloneFactory.at(
            signing_coordinator_child.signingMultisigFactory()
        )
    )
    expected_multisig_address = (
        threshold_signing_multisig_clone_factory.getCloneAddress(cohort_id)
    )
    cohort_multisig = nucypher_dependency.ThresholdSigningMultisig.at(
        expected_multisig_address
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
    testerchain,
):
    bob.start_learning_loop(now=True)

    # Create a proper PackedUserOperation using the helper function
    user_op = PackedUserOperation(
        sender=accounts[0].address,
        nonce=0,
        call_data=HexBytes("deadbeef"),
        verification_gas_limit=100000,
        call_gas_limit=100000,
        pre_verification_gas=21000,
        max_priority_fee_per_gas=1000000000,  # 1 gwei
        max_fee_per_gas=2000000000,  # 2 gwei
    )

    # Use the proper entrypoint address and chain_id for EIP-712 structured data
    entrypoint = accounts[2].address  # Using accounts[2] as entrypoint
    chain_id = testerchain.w3.eth.chain_id

    user_operation = user_op.to_eip712_struct(entrypoint, chain_id)

    signing_request = SignatureRequest(
        data=user_operation,
        cohort_id=cohort_id,
        chain_id=chain.chain_id,
        context=None,
        signature_type=SignatureType.EIP_712,
    )

    print("============= SIGNING REQUEST (NO CONDITION)==============")
    with pytest.raises(Ursula.NotEnoughUrsulas, match="Condition not configured"):
        _ = yield bob.request_threshold_signatures(
            signing_request=signing_request,
        )
    print("===================== SIGNING FAILED =====================")

    print("==================== SIGNING REQUEST ====================")
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

    threshold_signing_multisig_clone_factory = (
        nucypher_dependency.ThresholdSigningMultisigCloneFactory.at(
            signing_coordinator_child.signingMultisigFactory()
        )
    )
    multisig_address = threshold_signing_multisig_clone_factory.getCloneAddress(
        cohort_id
    )
    multisig = nucypher_dependency.ThresholdSigningMultisig.at(multisig_address)
    result = multisig.isValidSignature(
        encode_typed_data(full_message=user_operation).body,
        b"".join(r.signature for r in responses),
    )
    magic_value = EIP1271Auth.MAGIC_VALUE_BYTES
    assert result == magic_value, f"Invalid signature: {result} != {magic_value}"
    print("===================== SIGNING SUCCESSFUL =====================")
    yield
