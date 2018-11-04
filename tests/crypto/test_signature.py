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
