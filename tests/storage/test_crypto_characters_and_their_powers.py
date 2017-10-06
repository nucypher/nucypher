from nkms.characters import Alice, Ursula
import pytest

from nkms.crypto.hash import content_hash
from nkms.crypto.powers import CryptoPower, SigningKeypair, NoSigningPower


def test_signing_only_power_can_sign():
    signing_only = CryptoPower(power_ups=[SigningKeypair])
    alice = Alice(crypto_power=signing_only)
    alices_seal = alice.seal

    message = b"Llamas."
    content_hash(message)
    signature = alices_seal(message)
    verification = alice._crypto_power.verify(signature, message)

    assert verification


def test_signing_only_power_cannot_encrypt():
    signing_only = CryptoPower(power_ups=[SigningKeypair])
    alice = Alice(crypto_power=signing_only)
    ursula = Ursula()
    ursula.pubkey_collection = {'signing': "some_privkey_sig"}

    ursula_actor_id = "whatever actor id ends up being"

    cleartext = "This is Officer Rod Farva. Come in, Ursula!  Come in Ursula!"

    alice._actor_mapping[ursula_actor_id] = ursula
    with pytest.raises(NoSigningPower) as e_info:
        alice.encrypt_for(ursula_actor_id, cleartext)