from umbral.keys import UmbralPrivateKey

from nucypher.crypto.api import ecdsa_sign
from nucypher.crypto.signing import Signature


def test_signature_can_verify():
    privkey = UmbralPrivateKey.gen_key()
    message = b"attack at dawn"
    der_sig_bytes = ecdsa_sign(message, privkey)
    signature = Signature.from_bytes(der_sig_bytes, der_encoded=True)
    assert signature.verify(message, privkey.get_pubkey())


def test_signature_rs_serialization():
    privkey = UmbralPrivateKey.gen_key()
    message = b"attack at dawn"
    der_sig_bytes = ecdsa_sign(message, privkey)

    signature_from_der = Signature.from_bytes(der_sig_bytes, der_encoded=True)
    rs_sig_bytes = bytes(signature_from_der)
    assert len(rs_sig_bytes) == 64

    signature_from_rs = Signature.from_bytes(rs_sig_bytes, der_encoded=False)

    assert signature_from_rs == signature_from_der
    assert signature_from_rs == der_sig_bytes
    assert signature_from_rs.verify(message, privkey.get_pubkey())
