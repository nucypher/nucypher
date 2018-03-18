from nkms.characters import Ursula
from nkms.crypto.powers import SigningPower


def test_ursula_generates_self_signed_cert():
    ursula = Ursula(attach_server=False)
    cert, cert_private_key = ursula.generate_self_signed_certificate()
    public_key_numbers = ursula.public_key(SigningPower).to_cryptography_pubkey().public_numbers()
    assert cert.public_key().public_numbers() == public_key_numbers
