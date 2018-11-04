"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

import pytest
from eth_keys.datatypes import Signature as EthSignature

from nucypher.characters.lawful import Ursula
from nucypher.characters.unlawful import Vladimir
from nucypher.crypto.powers import SigningPower, CryptoPower
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


@pytest.mark.skip("To be implemented...?")
def test_federated_ursula_substantiates_stamp():
    assert False


def test_new_federated_ursula_announces_herself(ursula_federated_test_config):
    ursula_in_a_house, ursula_with_a_mouse = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                                                    quantity=2,
                                                                    know_each_other=False,
                                                                    network_middleware=MockRestMiddleware())

    # Neither Ursula knows about the other.
    assert ursula_in_a_house.known_nodes == ursula_with_a_mouse.known_nodes == {}

    ursula_in_a_house.remember_node(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes.values()
    assert not ursula_in_a_house in ursula_with_a_mouse.known_nodes.values()

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_teacher_node()

    assert ursula_with_a_mouse in ursula_in_a_house.known_nodes.values()
    assert ursula_in_a_house in ursula_with_a_mouse.known_nodes.values()


def test_blockchain_ursula_substantiates_stamp(blockchain_ursulas):
    first_ursula = list(blockchain_ursulas)[0]
    signature_as_bytes = first_ursula._evidence_of_decentralized_identity
    signature = EthSignature(signature_bytes=signature_as_bytes)
    proper_public_key_for_first_ursula = signature.recover_public_key_from_msg(bytes(first_ursula.stamp))
    proper_address_for_first_ursula = proper_public_key_for_first_ursula.to_checksum_address()
    assert proper_address_for_first_ursula == first_ursula.checksum_public_address

    # This method is a shortcut for the above.
    assert first_ursula._stamp_has_valid_wallet_signature


def test_blockchain_ursula_verifies_stamp(blockchain_ursulas):
    first_ursula = list(blockchain_ursulas)[0]

    # This Ursula does not yet have a verified stamp
    first_ursula.verified_stamp = False
    first_ursula.stamp_is_valid()

    # ...but now it's verified.
    assert first_ursula.verified_stamp


def test_vladimir_cannot_verify_interface_with_ursulas_signing_key(blockchain_ursulas):
    his_target = list(blockchain_ursulas)[4]

    # Vladimir has his own ether address; he hopes to publish it along with Ursula's details
    # so that Alice (or whomever) pays him instead of Ursula, even though Ursula is providing the service.

    # He finds a target and verifies that its interface is valid.
    assert his_target.interface_is_valid()

    # Now Vladimir imitates Ursula - copying her public keys and interface info, but inserting his ether address.
    vladimir = Vladimir.from_target_ursula(his_target, claim_signing_key=True)

    # Vladimir can substantiate the stamp using his own ether address...
    vladimir.substantiate_stamp(passphrase=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)
    vladimir.stamp_is_valid()

    # Now, even though his public signing key matches Ursulas...
    assert vladimir.stamp == his_target.stamp

    # ...he is unable to pretend that his interface is valid
    # because the interface validity check contains the canonical public address as part of its message.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.interface_is_valid()

    # Consequently, the metadata as a whole is also invalid.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.validate_metadata()


def test_vladimir_uses_his_own_signing_key(blockchain_alice, blockchain_ursulas):
    """
    Similar to the attack above, but this time Vladimir makes his own interface signature
    using his own signing key, which he claims is Ursula's.
    """
    his_target = list(blockchain_ursulas)[4]

    fraduluent_keys = CryptoPower(power_ups=Ursula._default_crypto_powerups)

    vladimir = Vladimir.from_target_ursula(target_ursula=his_target)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(vladimir.timestamp_bytes() + message)
    vladimir._interface_signature_object = signature

    vladimir.substantiate_stamp(passphrase=TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD)

    # With this slightly more sophisticated attack, his metadata does appear valid.
    vladimir.validate_metadata()

    # However, the actual handshake proves him wrong.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.verify_node(blockchain_alice.network_middleware)
