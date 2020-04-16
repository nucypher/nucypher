"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import pytest
from bytestring_splitter import BytestringSplitter, BytestringKwargifier, BytestringSplittingError,\
    VariableLengthBytestring
from nucypher.crypto.splitters import key_splitter, capsule_splitter

from constant_sorrow.constants import UNKNOWN_SENDER, NOT_SIGNED
from nucypher.characters.lawful import Enrico
from nucypher.crypto.api import secure_random
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import Signature

from nucypher.utilities.versioning import ByteVersioningMixin


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

    with pytest.raises(BytestringSplittingError):
        rebuilt_signature, rebuilt_bytes = splitter(signature + some_bytes, return_remainder=True)


def test_message_kit_serialization_via_enrico(enacted_federated_policy, federated_alice):

    # Enrico
    enrico = Enrico.from_alice(federated_alice, label=enacted_federated_policy.label)

    # Plaintext
    message = 'this is a message'
    plaintext_bytes = bytes(message, encoding='utf-8')

    # Create
    message_kit, signature = enrico.encrypt_message(message=plaintext_bytes)

    # Serialize
    message_kit_bytes = message_kit.to_bytes()

    # Deserialize
    the_same_message_kit = UmbralMessageKit.from_bytes(message_kit_bytes)

    # Confirm
    assert message_kit_bytes == the_same_message_kit.to_bytes()


def test_message_kit_versions(enacted_federated_policy, federated_alice):
    """
    Some day, for whatever reason, we need to insert some unforseeen
    relevant piece of data into the middle of the MessageKit.
    Can we add a new version of MessageKit that interoperates with bytestrings
    produced by existing previous versions that are already circulating in the wild?
    """

    class MessageKitVersion19(UmbralMessageKit):

        version = 19

        def __init__(self,
                     capsule,
                     pandemic=None,
                     sender_verifying_key=None,
                     ciphertext=None,
                     signature=NOT_SIGNED) -> None:

            self.pandemic = pandemic
            self.ciphertext = ciphertext
            self.capsule = capsule
            self.sender_verifying_key = sender_verifying_key
            self._signature = signature

        def __bytes__(self):
            return super().prepend_version(
                bytes(self.capsule) + bytes(
                    self.sender_verifying_key
                ) + bytes(
                    self.pandemic, 'utf-8'  # insert the prevailing pandemic here
                ) + VariableLengthBytestring(self.ciphertext))

        @classmethod
        def splitter(cls, *args, **kwargs):
            return BytestringKwargifier(
                MessageKitVersion19,
                capsule=capsule_splitter,
                sender_verifying_key=key_splitter,
                pandemic=BytestringSplitter(8),
                ciphertext=VariableLengthBytestring)

        def set_pandemic(self, string):
            self.pandemic = string

    enrico = Enrico.from_alice(federated_alice, label=enacted_federated_policy.label)
    message = 'this is a message'
    plaintext_bytes = bytes(message, encoding='utf-8')

    # the very existence of a subclass of UmbralMessageKit versioned 19 will make that the highest version
    # and it will now what is used for all newly created message kits

    mkit, signature = enrico.encrypt_message(message=plaintext_bytes)
    assert mkit.version == 19

    # set the prevailing pandemic of the day
    mkit.set_pandemic('covid-19')

    # and convert to bytes
    v19_mkit_bytes = bytes(mkit)

    # when instantiating from bytes we get an instance of MessageKitVersion19
    mkit19 = UmbralMessageKit.from_bytes(v19_mkit_bytes)
    assert mkit19.version == 19
    assert mkit19.pandemic == b'covid-19'

    v1 = (1).to_bytes(2, 'big')

    # along come some bytes representing an old message kit created during a more innocent time
    V1_mkit_bytes = (
        v1 + bytes(mkit.capsule) + bytes(mkit.sender_verifying_key) + VariableLengthBytestring(mkit.ciphertext))

    # lets just throw them into our base class
    v1_mkit = UmbralMessageKit.from_bytes(V1_mkit_bytes)

    # we have a good old fashioned version one UmbralMessageKit with no weird attributes from the future
    assert v1_mkit.version == 1
    assert hasattr(v1_mkit, 'pandemic') is False


def test_newer_version_than_installed_code_can_accomodate(enacted_federated_policy, federated_alice):

    """ This test will fail if we ever have a MessageKit version 99 """

    enrico = Enrico.from_alice(federated_alice, label=enacted_federated_policy.label)
    message = "I haven't been outside in days..."
    plaintext_bytes = bytes(message, encoding='utf-8')
    mkit, signature = enrico.encrypt_message(message=plaintext_bytes)
    # simulate an enrico from the future creating a message kit unsupported by this install

    v99 = (99).to_bytes(2, 'big')
    V99_mkit_bytes = (
        v99 + bytes(mkit.capsule) + bytes(mkit.sender_verifying_key) + VariableLengthBytestring(mkit.ciphertext))

    with pytest.raises(ByteVersioningMixin.NucypherNeedsUpdateException):
        # we should catch this NucypherNeedsUpdateException here
        UmbralMessageKit.from_bytes(V99_mkit_bytes)
