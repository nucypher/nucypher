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

from nucypher.characters.lawful import Enrico
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


def test_vladimir_cannot_verify_interface_with_ursulas_signing_key(blockchain_ursulas):
    his_target = list(blockchain_ursulas)[4]

    # Vladimir has his own ether address; he hopes to publish it along with Ursula's details
    # so that Alice (or whomever) pays him instead of Ursula, even though Ursula is providing the service.

    # He finds a target and verifies that its interface is valid.
    assert his_target.validate_interface()

    # Now Vladimir imitates Ursula - copying her public keys and interface info, but inserting his ether address.
    vladimir = Vladimir.from_target_ursula(his_target, claim_signing_key=True)

    # Vladimir can substantiate the stamp using his own ether address...
    vladimir._Ursula__substantiate_stamp()
    vladimir.validate_worker = lambda: True
    vladimir.validate_worker()  # lol

    # Now, even though his public signing key matches Ursulas...
    assert vladimir.stamp == his_target.stamp

    # ...he is unable to pretend that his interface is valid
    # because the interface validity check contains the canonical public address as part of its message.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.validate_interface()

    # Consequently, the metadata as a whole is also invalid.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.validate_metadata()


def test_vladimir_invalidity_without_stake(testerchain, blockchain_ursulas, blockchain_alice):
    his_target = list(blockchain_ursulas)[4]
    vladimir = Vladimir.from_target_ursula(target_ursula=his_target)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(vladimir.timestamp_bytes() + message)
    vladimir._Teacher__interface_signature = signature
    vladimir._Ursula__substantiate_stamp()

    # However, the actual handshake proves him wrong.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.verify_node(blockchain_alice.network_middleware.client, certificate_filepath="doesn't matter")


def test_vladimir_uses_his_own_signing_key(blockchain_alice, blockchain_ursulas):
    """
    Similar to the attack above, but this time Vladimir makes his own interface signature
    using his own signing key, which he claims is Ursula's.
    """
    his_target = list(blockchain_ursulas)[4]
    vladimir = Vladimir.from_target_ursula(target_ursula=his_target)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(vladimir.timestamp_bytes() + message)
    vladimir._Teacher__interface_signature = signature
    vladimir._Ursula__substantiate_stamp()

    vladimir._worker_is_bonded_to_staker = lambda: True
    vladimir._staker_is_really_staking = lambda: True
    vladimir.validate_worker()  # lol

    # With this slightly more sophisticated attack, his metadata does appear valid.
    vladimir.validate_metadata()

    # However, the actual handshake proves him wrong.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.verify_node(blockchain_alice.network_middleware.client, certificate_filepath="doesn't matter")


# TODO: Change name of this file, extract this test
def test_blockchain_ursulas_reencrypt(blockchain_ursulas, blockchain_alice, blockchain_bob, policy_value):
    label = b'bbo'

    # TODO: Make sample selection buffer configurable - #1061
    m = n = 10
    expiration = maya.now() + datetime.timedelta(days=35)

    _policy = blockchain_alice.grant(bob=blockchain_bob,
                                     label=label,
                                     m=m,
                                     n=n,
                                     expiration=expiration,
                                     value=policy_value)

    enrico = Enrico.from_alice(blockchain_alice, label)

    message = b"Oh, this isn't even BO. This is beyond BO. It's BBO."

    message_kit, signature = enrico.encrypt_message(message)

    blockchain_bob.start_learning_loop(now=True)
    blockchain_bob.join_policy(label, bytes(blockchain_alice.stamp))

    plaintext = blockchain_bob.retrieve(message_kit, alice_verifying_key=blockchain_alice.stamp, label=label,
                                        enrico=enrico)
    assert plaintext[0] == message

    # Let's consider also that a node may be down when granting
    blockchain_alice.network_middleware = NodeIsDownMiddleware()
    blockchain_alice.network_middleware.node_is_down(blockchain_ursulas[0])

    with pytest.raises(BlockchainPolicy.NotEnoughBlockchainUrsulas):
        _policy = blockchain_alice.grant(bob=blockchain_bob,
                                         label=b'another-label',
                                         m=m,
                                         n=n,
                                         expiration=expiration,
                                         value=policy_value)
