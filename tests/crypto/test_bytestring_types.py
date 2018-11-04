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
import pytest
from bytestring_splitter import BytestringSplitter

from nucypher.crypto.api import secure_random
from nucypher.crypto.signing import Signature


def test_split_two_signatures():
    """
    We make two random Signatures and concat them.  Then split them and show that we got the proper result.
    """
    sig1 = Signature.from_bytes(secure_random(64))
    sig2 = Signature.from_bytes(secure_random(64))
    sigs_concatted = sig1 + sig2
    two_signature_splitter = BytestringSplitter(Signature, Signature)
    rebuilt_sig1, rebuilt_sig2 = two_signature_splitter(sigs_concatted)
    assert (sig1, sig2) == (rebuilt_sig1, rebuilt_sig2)


def test_split_signature_from_arbitrary_bytes():
    how_many_bytes = 10
    signature = Signature.from_bytes(secure_random(64))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, how_many_bytes))

    rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes)


def test_trying_to_extract_too_many_bytes_raises_typeerror():
    how_many_bytes = 10
    too_many_bytes = 11
    signature = Signature.from_bytes(secure_random(64))
    some_bytes = secure_random(how_many_bytes)
    splitter = BytestringSplitter(Signature, (bytes, too_many_bytes))

    with pytest.raises(ValueError):
        rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes, return_remainder=True)
