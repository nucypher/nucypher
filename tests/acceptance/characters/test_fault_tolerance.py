import pytest
from eth_typing import ChecksumAddress
from nucypher_core import MetadataResponse, MetadataResponsePayload
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.acumen.perception import FleetSensor
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import TransactingPower
from tests.constants import TEST_ETH_PROVIDER_URI
from tests.utils.ursula import make_ursulas, start_pytest_ursula_services


def test_ursula_stamp_verification_tolerance(ursulas, mocker):
    #
    # Setup
    #

    lonely_learner, teacher, unsigned, *the_others = list(ursulas)

    warnings = []
    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # Make a bad identity evidence
    unsigned._Ursula__operator_signature = unsigned._Ursula__operator_signature[:-5] + (b'\x00' * 5)
    # Reset the metadata cache
    unsigned._metadata = None

    # Wipe known nodes!
    lonely_learner._Learner__known_nodes = FleetSensor(domain=TEMPORARY_DOMAIN)
    lonely_learner._current_teacher_node = teacher
    lonely_learner.remember_node(teacher)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned) in warning
    assert "Verification Failed" in warning  # TODO: Cleanup logging templates

    # TODO: Buckets!  #567
    # assert unsigned not in lonely_learner.known_nodes

    # minus 2: self and the unsigned ursula.
    # assert len(lonely_learner.known_nodes) == len(ursulas) - 2
    assert teacher in lonely_learner.known_nodes

    # Learn about a node with a badly signed payload

    def bad_bytestring_of_known_nodes():
        # Signing with the learner's signer instead of the teacher's signer
        response_payload = MetadataResponsePayload(
            timestamp_epoch=teacher.known_nodes.timestamp.epoch, announce_nodes=[]
        )
        response = MetadataResponse(
            signer=lonely_learner.stamp.as_umbral_signer(), payload=response_payload
        )
        return bytes(response)

    mocker.patch.object(
        teacher, "bytestring_of_known_nodes", bad_bytestring_of_known_nodes
    )

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_teacher_node(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 2
    warning = warnings[1]['log_format']
    assert str(teacher) in warning
    assert "Failed to verify MetadataResponse from Teacher" in warning  # TODO: Cleanup logging templates


def test_invalid_operators_tolerance(
    testerchain,
    test_registry,
    ursulas,
    threshold_staking,
    taco_application_agent,
    ursula_test_config,
    mocker,
    deployer_account,
):
    #
    # Setup
    #
    (
        creator,
        _staking_provider,
        operator_address,
        *everyone_else,
    ) = testerchain.client.accounts

    existing_ursula, other_ursula, *the_others = list(ursulas)

    # We start with an ursula with no tokens staked
    owner, _, _ = threshold_staking.rolesOf(_staking_provider, sender=deployer_account)
    assert owner == NULL_ADDRESS

    # make an staking_providers and some stakes
    min_authorization = taco_application_agent.get_min_authorization()
    threshold_staking.setRoles(_staking_provider, sender=deployer_account)
    threshold_staking.authorizationIncreased(
        _staking_provider, 0, min_authorization, sender=deployer_account
    )

    # now lets bond this worker
    tpower = TransactingPower(
        account=_staking_provider, signer=Web3Signer(testerchain.client)
    )
    taco_application_agent.bond_operator(
        staking_provider=_staking_provider,
        operator=operator_address,
        transacting_power=tpower,
    )

    # Make the Operator
    ursulas = make_ursulas(ursula_test_config, [_staking_provider], [operator_address])
    ursula = ursulas[0]
    ursula.run(
        preflight=False,
        discovery=False,
        start_reactor=False,
        eager=True,
        block_until_ready=True,
    )  # "start" services
    start_pytest_ursula_services(ursula=ursula)

    # The worker is valid and can be verified (even with the force option)
    ursula.verify_node(
        force=True,
        registry=test_registry,
        network_middleware_client=ursula.network_middleware.client,
        eth_endpoint=ursula.eth_endpoint,
    )
    # In particular, we know that it's bonded to a staker who is really staking.
    assert ursula.is_confirmed
    assert ursula._staking_provider_is_really_staking(
        registry=test_registry, eth_endpoint=TEST_ETH_PROVIDER_URI
    )

    # OK. Now we learn about this new worker.
    assert existing_ursula.remember_node(ursula)

    # Mock that ursula stops staking
    def mock_is_authorized(staking_provider: ChecksumAddress):
        if staking_provider == ursula.checksum_address:
            return False

        return True

    mocker.patch.object(
        taco_application_agent, "is_authorized", side_effect=mock_is_authorized
    )

    # OK...so...the staker is not staking anymore ...
    assert not ursula._staking_provider_is_really_staking(
        registry=test_registry, eth_endpoint=TEST_ETH_PROVIDER_URI
    )

    # ... but the worker node still is "verified" (since we're not forcing on-chain verification)
    ursula.verify_node(
        registry=test_registry,
        network_middleware_client=ursula.network_middleware.client,
    )

    # If we force, on-chain verification, the worker is of course not verified
    with pytest.raises(ursula.NotStaking):
        ursula.verify_node(
            force=True,
            registry=test_registry,
            network_middleware_client=ursula.network_middleware.client,
            eth_endpoint=TEST_ETH_PROVIDER_URI,
        )

    #
    # TODO node verification is cached for a certain amount of time before rechecking; so unclear
    #  how to adjust the following code.
    #
    # warnings = []
    # def warning_trapper(event):
    #     if event['log_level'] == LogLevel.warn:
    #         warnings.append(event)

    # Let's learn from this invalid node
    # existing_ursula._current_teacher_node = ursula
    # globalLogPublisher.addObserver(warning_trapper)
    # existing_ursula.learn_from_teacher_node(eager=True)
    # # lonely_blockchain_learner.remember_node(worker)  # The same problem occurs if we directly try to remember this node
    # globalLogPublisher.removeObserver(warning_trapper)

    # TODO: What should we really check here? (#1075)
    # assert len(warnings) == 1
    # warning = warnings[-1]['log_format']
    # assert str(ursula) in warning
    # assert "no active stakes" in warning  # TODO: Cleanup logging templates
    # assert ursula not in existing_ursula.known_nodes

    # TODO: Write a similar test but for detached worker (#1075)
    #   Unclear that this case is still valid - detached workers get automatically shut-down
