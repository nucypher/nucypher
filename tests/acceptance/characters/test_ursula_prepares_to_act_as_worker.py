"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import datetime
import maya
import pytest
from eth_account._utils.signing import to_standard_signature_bytes

from nucypher.characters.lawful import Enrico, Ursula
from nucypher.characters.unlawful import Vladimir
from nucypher.crypto.utils import verify_eip_191
from nucypher.crypto.powers import SigningPower
from nucypher.policy.policies import BlockchainPolicy
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD
from tests.utils.middleware import NodeIsDownMiddleware
from tests.utils.ursula import make_decentralized_ursulas


@pytest.mark.usefixtures("blockchain_ursulas")
def test_stakers_bond_to_ursulas(testerchain, test_registry, stakers, ursula_decentralized_test_config):
    ursulas = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                         stakers_addresses=testerchain.stakers_accounts,
                                         workers_addresses=testerchain.ursulas_accounts)

    assert len(ursulas) == len(stakers)
    for ursula in ursulas:
        ursula.validate_worker(registry=test_registry)
        assert ursula.verified_worker


def test_blockchain_ursula_substantiates_stamp(blockchain_ursulas):
    first_ursula = list(blockchain_ursulas)[0]
    signature_as_bytes = first_ursula.decentralized_identity_evidence
    signature_as_bytes = to_standard_signature_bytes(signature_as_bytes)
    assert verify_eip_191(address=first_ursula.worker_address,
                          message=bytes(first_ursula.stamp),
                          signature=signature_as_bytes)

    # This method is a shortcut for the above.
    assert first_ursula._stamp_has_valid_signature_by_worker()


def test_blockchain_ursula_verifies_stamp(blockchain_ursulas):
    first_ursula = list(blockchain_ursulas)[0]

    # This Ursula does not yet have a verified stamp
    first_ursula.verified_stamp = False
    first_ursula.validate_worker()

    # ...but now it's verified.
    assert first_ursula.verified_stamp


def remote_vladimir(**kwds):
    vladimir = Vladimir.from_target_ursula(**kwds)
    remote_vladimir = Ursula.from_metadata_bytes(bytes(vladimir.metadata())).mature()
    return remote_vladimir


def test_vladimir_cannot_verify_interface_with_ursulas_signing_key(blockchain_ursulas):
    his_target = list(blockchain_ursulas)[4]

    # Vladimir has his own ether address; he hopes to publish it along with Ursula's details
    # so that Alice (or whomever) pays him instead of Ursula, even though Ursula is providing the service.

    # He finds a target and verifies that its interface is valid.
    assert his_target.validate_metadata_signature()

    # Now Vladimir imitates Ursula - copying her public keys and interface info, but inserting his ether address.
    vladimir = remote_vladimir(target_ursula=his_target)

    # Now, even though his public signing key matches Ursulas...
    assert vladimir.metadata().verifying_key == his_target.stamp.as_umbral_pubkey()

    # ...he is unable to pretend that his interface is valid
    # because the validity check contains the canonical public address as part of its message.
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata_signature()

    # Consequently, the metadata as a whole is also invalid.
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata()


def test_vladimir_uses_his_own_signing_key(blockchain_alice, blockchain_ursulas, test_registry):
    """
    Similar to the attack above, but this time Vladimir makes his own interface signature
    using his own signing key, which he claims is Ursula's.
    """
    his_target = list(blockchain_ursulas)[4]
    vladimir = remote_vladimir(target_ursula=his_target,
                               sign_metadata=True)

    # The metadata signature does not match the verifying key
    with pytest.raises(vladimir.InvalidNode, match="Metadata signature is invalid"):
        vladimir.validate_metadata_signature()

    # Let's try again, but this time put our own key in the metadata, too
    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    # With this slightly more sophisticated attack, his metadata does appear valid.
    # In fact, we pass the decentralized evidence verification too,
    # since the worker address is derived from it - so it is valid automatically.
    vladimir.validate_metadata()

    # But since the derived worker address is bogus, the staker-worker bond check fails.
    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    message = f"Worker {vladimir.worker_address} is not bonded"
    with pytest.raises(vladimir.UnbondedWorker, match=message):
        vladimir.validate_metadata(registry=test_registry)


def test_vladimir_invalidity_without_stake(testerchain, blockchain_ursulas, blockchain_alice):
    his_target = list(blockchain_ursulas)[4]

    vladimir = remote_vladimir(target_ursula=his_target,
                               substitute_verifying_key=True,
                               sign_metadata=True)

    # All the signature validations will pass (without the registry check)
    vladimir.validate_metadata()

    # But the actual handshake proves him wrong.
    message = "Wallet address swapped out.  It appears that someone is trying to defraud this node."
    with pytest.raises(vladimir.InvalidNode, match=message):
        vladimir.verify_node(blockchain_alice.network_middleware.client, certificate_filepath="doesn't matter")


# TODO: Change name of this file, extract this test
def test_blockchain_ursulas_reencrypt(blockchain_ursulas, blockchain_alice, blockchain_bob, policy_value):
    label = b'bbo'

    # TODO: Make sample selection buffer configurable - #1061
    threshold = shares = 10
    expiration = maya.now() + datetime.timedelta(days=35)

    _policy = blockchain_alice.grant(bob=blockchain_bob,
                                     label=label,
                                     threshold=threshold,
                                     shares=shares,
                                     expiration=expiration,
                                     value=policy_value)

    enrico = Enrico.from_alice(blockchain_alice, label)

    message = b"Oh, this isn't even BO. This is beyond BO. It's BBO."

    message_kit = enrico.encrypt_message(message)

    blockchain_bob.start_learning_loop(now=True)

    plaintexts = blockchain_bob.retrieve_and_decrypt([message_kit],
                                                     encrypted_treasure_map=_policy.treasure_map,
                                                     alice_verifying_key=blockchain_alice.stamp.as_umbral_pubkey())
    assert plaintexts == [message]

    # Let's consider also that a node may be down when granting
    blockchain_alice.network_middleware = NodeIsDownMiddleware()
    blockchain_alice.network_middleware.node_is_down(blockchain_ursulas[0])

    with pytest.raises(BlockchainPolicy.NotEnoughUrsulas):
        _policy = blockchain_alice.grant(bob=blockchain_bob,
                                         label=b'another-label',
                                         threshold=threshold,
                                         shares=shares,
                                         expiration=expiration,
                                         value=policy_value)
