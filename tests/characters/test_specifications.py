import pytest
from nucypher.characters.control.specifications import AliceSpecification
from nucypher.characters.control.specifications.exceptions import SpecificationError


def test_alice_spec_validate(federated_alice, federated_bob):

    createPolicy = AliceSpecification.get_serializer('create_policy')
    specs = AliceSpecification.get_specifications('create_policy')

    with pytest.raises(SpecificationError) as e:
        result = createPolicy.load({})

