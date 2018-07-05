import pytest

from nucypher.characters import Ursula
from nucypher.crypto.powers import SigningPower


@pytest.mark.usesfixtures('testerchain')
def test_ursula_generates_self_signed_cert():
    ursula = Ursula(is_me=False, rest_port=5000, rest_host="not used", federated_only=True)
    cert, cert_private_key = ursula.generate_self_signed_certificate()
    public_key_numbers = ursula.public_key(SigningPower).to_cryptography_pubkey().public_numbers()
    assert cert.public_key().public_numbers() == public_key_numbers
