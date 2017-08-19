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
