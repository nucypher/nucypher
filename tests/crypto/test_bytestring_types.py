import pytest

from nkms.crypto import api
from nkms.crypto.api import secure_random
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from umbral.bignum import BigNum
from umbral.fragments import KFrag
from umbral.point import Point


def test_split_two_signatures():
    """
    We make two random Signatures and concat them.  Then split them and show that we got the proper result.
    """
    sig1, sig2 = Signature(secure_random(65)), Signature(secure_random(65))
    sigs_concatted = sig1 + sig2
    two_signature_splitter = BytestringSplitter(Signature, Signature)
    rebuilt_sig1, rebuilt_sig2 = two_signature_splitter(sigs_concatted)
    assert (sig1, sig2) == (rebuilt_sig1, rebuilt_sig2)


def test_split_signature_from_arbitrary_bytes():
    how_many_bytes = 10
    signature = Signature(secure_random(65))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, how_many_bytes))

    rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes)


def test_split_kfrag_from_arbitrary_bytes():
    rand_id = b'\x00' + api.secure_random(32)
    rand_key = b'\x00' + api.secure_random(32)

    KFrag(id_=BigNum.gen_rand(), key=BigNum.gen_rand(), x=Point.gen_rand(), u1=Point.gen_rand(), z1=BigNum.gen_rand(),
          z2=BigNum.gen_rand())


    # TODO: The rest of this test no longer makes sense with the new KFrag class.
    how_many_bytes = 10
    some_bytes = secure_random(how_many_bytes)

    splitter = BytestringSplitter(KFrag, (bytes, how_many_bytes))
    rebuilt_kfrag, rebuilt_bytes = splitter(kfrag + some_bytes)
    assert kfrag == rebuilt_kfrag


def test_trying_to_extract_too_many_bytes_raises_typeerror():
    how_many_bytes = 10
    too_many_bytes = 11
    signature = Signature(secure_random(65))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, too_many_bytes))

    with pytest.raises(ValueError):
        rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes, return_remainder=True)
