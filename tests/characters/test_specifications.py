import pytest
from marshmallow.exceptions import ValidationError
from nucypher.characters.control.specifications import AliceSpecification


def test_alice_spec_validate(federated_alice, federated_bob):

    createPolicy = AliceSpecification.get_spec('create_policy')
    specs = AliceSpecification.get_specifications('create_policy')

    with pytest.raises(ValidationError) as e:
        result = createPolicy.load({})

