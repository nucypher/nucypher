import pytest
from eth_typing import ChecksumAddress
from nucypher_core import MetadataResponse, MetadataResponsePayload
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.acumen.perception import FleetSensor
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import TEST_ETH_PROVIDER_URI


def test_ursula_stamp_verification_tolerance(ursulas, mocker):
    lonely_learner, peer, unsigned, *the_others = list(ursulas)

    warnings = []
    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # Make a bad identity evidence
    unsigned._Ursula__operator_signature = unsigned._Ursula__operator_signature[:-12] + (b'\x00' * 12)
    # Reset the metadata cache
    unsigned._metadata = None

    # Wipe known nodes!
    lonely_learner.peers = FleetSensor(domain=TEMPORARY_DOMAIN_NAME)
    lonely_learner._current_peer = peer
    lonely_learner.remember_peer(peer)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_peer(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during peering, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned.rest_url()) in warning
    assert "Suspicious Activity" in warning

    # The unsigned node is not in the peer list
    assert unsigned not in lonely_learner.peers

    # minus 2: self and the unsigned ursula.
    # assert len(lonely_learner.peers) == len(ursulas) - 2
    assert peer in lonely_learner.peers

    # Learn about a node with a badly signed payload

    def bad_bytestring_of_peers():
        # Signing with the learner's signer instead of the peer's signer
        response_payload = MetadataResponsePayload(
            timestamp_epoch=peer.peers.timestamp.epoch, announce_nodes=[]
        )
        response = MetadataResponse(
            signer=lonely_learner.stamp.as_umbral_signer(), payload=response_payload
        )
        return bytes(response)

    mocker.patch.object(
        peer, "bytestring_of_peers", bad_bytestring_of_peers
    )

    globalLogPublisher.addObserver(warning_trapper)
    lonely_learner.learn_from_peer(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 2
    warning = warnings[1]['log_format']
    assert str(peer) in warning
    assert "Failed to verify MetadataResponse from Teacher" in warning


@pytest.mark.usefixtures("bond_operators")
def test_invalid_operators_tolerance(
    testerchain,
    test_registry,
    ursulas,
    threshold_staking,
    taco_application_agent,
    mocker,
    deployer_account,
):

    _staking_provider = testerchain.accounts.stake_provider_wallets[0]
    existing_ursula, other_ursula, ursula, *the_others = list(ursulas)

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
    existing_ursula.remember_peer(ursula)
    assert ursula in existing_ursula.peers

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

    warnings = []
    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    # Let's learn from this invalid node
    existing_ursula._current_peer = ursula
    globalLogPublisher.addObserver(warning_trapper)
    existing_ursula.learn_from_peer(eager=True)
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 1
    warning = warnings[-1]['log_format']
    assert str(ursula.checksum_address) in warning
    assert f"{ursula.checksum_address} is not staking" in warning
    assert ursula not in existing_ursula.peers
