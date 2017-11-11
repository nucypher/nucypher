from nkms.crypto.api import secure_random
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter


def test_split_two_signatures():
    """
    We make two random Signatures and concat them.  Then split them and show that we got the proper result.
    """
    sig1, sig2 = Signature(secure_random(65)), Signature(secure_random(65))
    two_signature_splitter = BytestringSplitter(Signature, Signature)
    rebuilt_sig1, rebuilt_sig2 = two_signature_splitter(sig1 + sig2)
    assert (sig1, sig2) == (rebuilt_sig1, rebuilt_sig2)
