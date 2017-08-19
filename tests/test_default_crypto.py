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
    sk_a = b'a' * 32
    sk_b = b'b' * 32
    pk_a = pre.priv2pub(sk_a)
    pk_b = pre.priv2pub(sk_b)
    msg = b'Hello world'
    rk_ab = pre.rekey(sk_a, pk_b)

    emsg_a = pre.encrypt(pk_a, msg)
    emsg_b = pre.reencrypt(rk_ab, emsg_a)

    assert pre.decrypt(sk_a, emsg_a) == msg
    assert pre.decrypt(sk_b, emsg_a) != msg
    assert pre.decrypt(sk_b, emsg_b) == msg
