from nkms.crypto import default_algorithm
from nkms.crypto import symmetric_from_algorithm
from nkms.crypto import pre_from_algorithm
from nkms import crypto


def test_symmetric():
    Cipher = symmetric_from_algorithm(default_algorithm)
    key = crypto.random(Cipher.KEY_SIZE)
    cipher = Cipher(key)
    data = b'Hello world' * 10

    edata = cipher.encrypt(data)
    assert edata != data
    assert cipher.decrypt(edata) == data


def test_pre():
    pre = pre_from_algorithm(default_algorithm)

    sk_alice = b'a' * 32
    sk_bob = b'b' * 32

    pk_alice = pre.priv2pub(sk_alice)
    pk_bob = pre.priv2pub(sk_bob)

    cleartext = b'Hello world'

    cyphertext_for_alice = pre.encrypt(pk_alice, cleartext)
    assert pre.decrypt(sk_alice, cyphertext_for_alice) == cleartext  # Alice can read her message.
    assert pre.decrypt(sk_bob, cyphertext_for_alice) != cleartext  # But Bob can't!

    # Now we make a re-encryption key from Alice to Bob
    rk_alice_bob = pre.rekey(sk_alice, pk_bob, sk_bob)
    # Use the key on Alice's cyphertext...
    cyphertext_for_bob = pre.reencrypt(rk_alice_bob, cyphertext_for_alice)
    # ...and sure enough, Bob can read it!
    assert pre.decrypt(sk_bob, cyphertext_for_bob) == cleartext
