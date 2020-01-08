import pytest

from nucypher.characters.control.specifications.alice import CreatePolicy
from nucypher.characters.control.specifications.exceptions import SpecificationError


def test_alice_spec_validate(federated_alice, federated_bob):

    with pytest.raises(SpecificationError) as e:
        _result = CreatePolicy().load(dict())
