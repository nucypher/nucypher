import pytest

from nucypher.characters import Ursula
from nucypher.crypto.powers import SigningPower


@pytest.mark.usesfixtures('testerchain')
def test_ursula_generates_self_signed_cert():
    ursula = Ursula(is_me=False, rest_port=5000, rest_host="not used", federated_only=True)
    cert, cert_private_key = ursula.generate_self_signed_certificate()
    public_key_numbers = ursula.public_key(SigningPower).to_cryptography_pubkey().public_numbers()
    assert cert.public_key().public_numbers() == public_key_numbers


@pytest.mark.skip
def test_federated_ursula_substantiates_stamp():
    assert False


def test_blockchain_ursula_substantiates_stamp(mining_ursulas):
    first_ursula = list(mining_ursulas)[0]
    signature = first_ursula.evidence_of_decentralized_identity
    proper_public_key_for_first_ursula = signature.recover_public_key_from_msg(bytes(first_ursula.stamp))
    proper_address_for_first_ursula = proper_public_key_for_first_ursula.to_checksum_address()
    assert proper_address_for_first_ursula == first_ursula.checksum_public_address
