import pytest
from marshmallow import validates_schema
import maya
import datetime

from nucypher.characters.control.specifications.alice import CreatePolicy, GrantPolicy
from nucypher.characters.control.specifications.exceptions import (
    InvalidInputData, InvalidArgumentCombo, SpecificationError)
from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema

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


def test_treasuremap_validation():
    """Tell people exactly what's wrong with their treasuremaps"""

    class TreasureMapsOnly(BaseSchema):

        tmap = fields.TreasureMap()

    # this will raise a base64 error
    with pytest.raises(SpecificationError) as e:
        TreasureMapsOnly().load({'tmap': "your face looks like a treasure map"})

    # assert that field name is in the error message
    assert "Could not parse tmap" in str(e)
    assert "Invalid base64-encoded string" in str(e)

    # valid base64 but invalid treasuremap
    with pytest.raises(SpecificationError) as e:
        TreasureMapsOnly().load({'tmap': "VGhpcyBpcyB0b3RhbGx5IG5vdCBhIHRyZWFzdXJlbWFwLg=="})

    assert "Could not parse tmap" in str(e)
    assert "Can't split a message with more bytes than the original splittable" in str(e)

    # a valid treasuremap for once...
    result = TreasureMapsOnly().load({'tmap': "dAYjo1M+OWFWXS/EkRGGBUJ6ywgGczmbELGbncfYT1W51k/EBO6y/LwSIeoQcrT/NzE25OXnsnnwOzwoZxT5oE7fhO+HbJPiGTt1Fl4iCvVrwxuJWIk0Nrw9WslSNBzAAAABHAM2ndUrO/67tZnGmF8ca1U8h09k2Qsn3gohnEP2M4aIfwPxG9F2jOqSS7OVoBsNnziS0qdYqMXmPPMnNrUPyR4PfB+9RmvtufpZ1DbbP4MEyxL1qL4xrmNhr6AYSMbnJD6FA3Qb0AGzgLrvTrO7qaWSJ2mxKMyGNnC/FeZhjg4AeuTfuEGEkogqeL/uMTNrl5vG3JwNIXFVsPY3sXR743ZKpP4ypu8HFj8BoqSfxleRmcwbANHQlSdwBd+/NJLcdqQCVuB1UdFDJPCJ3HxvjHIRhxWHTtuQ4L/HIjxTHoRsS/CFwjembIWhqpxqfswnxmKRQ5hCosO6iqK3aRYkDpOQMPwqgkv0diRBx5AC7Fj1nSfuXlpJix8PLxcy"})
    assert isinstance(result['tmap'], bytes)


def test_messagekit_validation():
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
        MessageKitsOnly().load({'mkit': "VGhpcyBpcyB0b3RhbGx5IG5vdCBhIHRyZWFzdXJlbWFwLg=="})

    assert "Could not parse mkit" in str(e)
    assert "Not enough bytes to constitute message types" in str(e)

    # test a valid messagekit
    result = MessageKitsOnly().load({'mkit': "ApZrJG9HOoNM7F6YZiiMhjRmWcMWP3rKmNLrsuAwdxh7A1cMPdJ5wppSU3LUgmvbJMiddZzsJKw0iJ1Vn1ax4TsmRqSKyR5NBEescZjTzX8fn7wzfwL0Q/vyIL9XFCi3nHACaNPrLk8yON7fAD/LDndn9BrdBRtM3lEXJ43tesa+v/g7i1uQ7HqAp2SDtQTrqyWQ3oc3xx0+TDN2ASvlYm+yed1/B3EM1I/ItghTsrDegoroVeYQbeTEbbs+PR9OgPyLUoXmDricfc6OdTaYZh4ZviXo6XpTPboQ6tv32pDqmoVY8TkPSmPkq5ZC7dD9SeModP92/A=="})
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
    assert "Unknown OpenSSL error." in str(e)

    result = BobKeyInputRequirer().load(dict(
        bobkey = federated_bob.public_keys(DecryptingPower).hex()))
    assert isinstance(result['bobkey'], bytes)
