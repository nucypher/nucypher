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


from base64 import b64encode

import datetime
import maya
import pytest

from nucypher.characters.control.specifications.fields.treasuremap import TreasureMap
from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.alice import GrantPolicy
from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications.exceptions import SpecificationError, InvalidInputData, InvalidArgumentCombo
from nucypher.crypto.powers import DecryptingPower


def test_various_field_validations_by_way_of_alice_grant(federated_bob):
    """ test some semi-complex validation situations """

    with pytest.raises(InvalidInputData):
        GrantPolicy().load(dict())

    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)

    data = {
        'bob_encrypting_key': bytes(bob_encrypting_key).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'm': 5,
        'n': 6,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        'label': 'cats the animal',
        'rate': 1000,
        'value': 3000,
    }

    # validate data with both rate and value fails validation
    with pytest.raises(InvalidArgumentCombo) as e:
        GrantPolicy().load(data)

    # remove value and now it works
    del data['value']
    result = GrantPolicy().load(data)
    assert result['label'] == b'cats the animal'

    # validate that negative "m" value fails
    data['m'] = -5
    with pytest.raises(SpecificationError) as e:
        GrantPolicy().load(data)

    # validate that m > n fails validation
    data['m'] = data['n'] + 19
    with pytest.raises(SpecificationError) as e:
        GrantPolicy().load(data)


def test_treasuremap_validation(enacted_federated_policy):
    """Tell people exactly what's wrong with their treasuremaps"""

    class TreasureMapsOnly(BaseSchema):
        tmap = TreasureMap(federated_only=True)

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        TreasureMapsOnly().load({'tmap': "your face looks like a treasure map"})

    # assert that field name is in the error message
    assert "Could not parse tmap" in str(e)
    assert "Invalid base64-encoded string" in str(e)

    # valid base64 but invalid treasuremap
    with pytest.raises(InvalidInputData) as e:
        TreasureMapsOnly().load({'tmap': "VGhpcyBpcyB0b3RhbGx5IG5vdCBhIHRyZWFzdXJlbWFwLg=="})

    assert "Could not parse tmap" in str(e)
    assert "Can't split a message with more bytes than the original splittable" in str(e)

    # a valid treasuremap for once...
    tmap_bytes = bytes(enacted_federated_policy.treasure_map)
    tmap_b64 = b64encode(tmap_bytes)
    result = TreasureMapsOnly().load({'tmap': tmap_b64.decode()})
    assert isinstance(result['tmap'], bytes)


def test_messagekit_validation(capsule_side_channel):
    """Ensure that our users know exactly what's wrong with their message kit input"""

    class MessageKitsOnly(BaseSchema):

        mkit = fields.UmbralMessageKit()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        MessageKitsOnly().load({'mkit': "I got a message for you"})

    # assert that field name is in the error message
    assert "Could not parse mkit" in str(e)
    assert "Incorrect padding" in str(e)

    # valid base64 but invalid treasuremap
    with pytest.raises(SpecificationError) as e:
        MessageKitsOnly().load({'mkit': "V3da"})

    assert "Could not parse mkit" in str(e)
    assert "Can't split a message with more bytes than the original splittable." in str(e)

    # test a valid messagekit
    valid_kit = capsule_side_channel.messages[0][0]
    kit_bytes = bytes(valid_kit)
    kit_b64 = b64encode(kit_bytes)
    result = MessageKitsOnly().load({'mkit': kit_b64.decode()})
    assert isinstance(result['mkit'], bytes)


def test_key_validation(federated_bob):

    class BobKeyInputRequirer(BaseSchema):
        bobkey = fields.Key()

    with pytest.raises(SpecificationError) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(SpecificationError) as e:
        BobKeyInputRequirer().load({'bobkey': "I am the key to nothing"})
    assert "non-hexadecimal number found in fromhex()" in str(e)
    assert "bobkey" in str(e)

    with pytest.raises(SpecificationError) as e:
        # lets just take a couple bytes off
        BobKeyInputRequirer().load({'bobkey': "02f0cb3f3a33f16255d9b2586e6c56570aa07bbeb1157e169f1fb114ffb40037"})
    assert "Could not convert input for bobkey to an Umbral Key" in str(e)
    assert "xpected 33 bytes, got 32" in str(e)

    result = BobKeyInputRequirer().load(dict(bobkey=bytes(federated_bob.public_keys(DecryptingPower)).hex()))
    assert isinstance(result['bobkey'], bytes)
