import pytest
from eth_keys.datatypes import Signature as EthSignature

from nucypher.characters import Ursula
from nucypher.crypto.powers import SigningPower, CryptoPower
from nucypher.utilities.sandbox import MockRestMiddleware, make_ursulas


@pytest.mark.skip("To be implemented...?")
def test_federated_ursula_substantiates_stamp():
    assert False


def test_new_ursula_announces_herself(testerchain):
    origin, ursula_here, ursula_there, *some_people = testerchain.interface.w3.eth.accounts
    ursula_in_a_house, ursula_with_a_mouse = make_ursulas(ether_addresses=[ursula_here, ursula_there],
                                                          know_each_other=False,
                                                          network_middleware=MockRestMiddleware())

    # Neither Ursula knows about the other.
    assert ursula_in_a_house._known_nodes == ursula_with_a_mouse._known_nodes == {}

    ursula_in_a_house.remember_node(ursula_with_a_mouse)

    # OK, now, ursula_in_a_house knows about ursula_with_a_mouse, but not vice-versa.
    assert ursula_with_a_mouse in ursula_in_a_house._known_nodes.values()
    assert not ursula_in_a_house in ursula_with_a_mouse._known_nodes.values()

    # But as ursula_in_a_house learns, she'll announce herself to ursula_with_a_mouse.
    ursula_in_a_house.learn_from_teacher_node()

    assert ursula_with_a_mouse in ursula_in_a_house._known_nodes.values()
    assert ursula_in_a_house in ursula_with_a_mouse._known_nodes.values()


def test_blockchain_ursula_substantiates_stamp(mining_ursulas):
    first_ursula = list(mining_ursulas)[0]
    signature_as_bytes = first_ursula._evidence_of_decentralized_identity
    signature = EthSignature(signature_bytes=signature_as_bytes)
    proper_public_key_for_first_ursula = signature.recover_public_key_from_msg(bytes(first_ursula.stamp))
    proper_address_for_first_ursula = proper_public_key_for_first_ursula.to_checksum_address()
    assert proper_address_for_first_ursula == first_ursula.checksum_public_address

    # This method is a shortcut for the above.
    assert first_ursula._stamp_has_valid_wallet_signature


def test_blockchain_ursula_verifies_stamp(mining_ursulas):
    first_ursula = list(mining_ursulas)[0]

    # This Ursula does not yet have a verified stamp
    assert not first_ursula.verified_stamp
    first_ursula.stamp_is_valid()

    # ...but now it's verified.
    assert first_ursula.verified_stamp


def test_vladimir_cannot_verify_interface_with_ursulas_signing_key(mining_ursulas):
    his_target = list(mining_ursulas)[4]

    # Vladimir has his own ether address; he hopes to publish it along with Ursula's details
    # so that Alice (or whomever) pays him instead of Ursula, even though Ursula is providing the service.
    vladimir_ether_address = '0xE57bFE9F44b819898F47BF37E5AF72a0783e1141'

    # Vladimir imitates Ursula - copying her public keys and interface info, but inserting his ether address.
    vladimir = Ursula(crypto_power=his_target._crypto_power,
                      rest_host=his_target.rest_information()[0].host,
                      rest_port=his_target.rest_information()[0].port,
                      checksum_address=vladimir_ether_address,
                      interface_signature=his_target._interface_signature,
                      is_me=False)

    # Vladimir can substantiate the stamp using his own ether address...
    vladimir.substantiate_stamp()
    vladimir.stamp_is_valid()

    # ...however, the signature for the interface info isn't valid.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.interface_is_valid()

    # Consequently, the metadata isn't valid.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.validate_metadata()


def test_vladimir_uses_his_own_signing_key(alice, mining_ursulas):
    """
    Similar to the attack above, but this time Vladimir makes his own interface signature
    using his own signing key, which he claims is Ursula's.
    """
    his_target = list(mining_ursulas)[4]
    vladimir_ether_address = '0xE57bFE9F44b819898F47BF37E5AF72a0783e1141'

    fraduluent_keys = CryptoPower(power_ups=Ursula._default_crypto_powerups)

    vladimir = Ursula(crypto_power=fraduluent_keys,
                      rest_host=his_target.rest_information()[0].host,
                      rest_port=his_target.rest_information()[0].port,
                      checksum_address=vladimir_ether_address,
                      certificate=his_target.rest_server_certificate(),
                      is_me=False)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(message)
    vladimir._interface_signature_object = signature

    vladimir.substantiate_stamp()

    # With this slightly more sophisticated attack, his metadata does appear valid.
    vladimir.validate_metadata()

    # However, the actual handshake proves him wrong.
    with pytest.raises(vladimir.InvalidNode):
        vladimir.verify_node(alice.network_middleware)
