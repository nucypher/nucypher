import pytest

from nkms.policy.models import PolicyManagerForAlice
from tests.test_utilities import ALICE, NUMBER_OF_URSULAS_IN_NETWORK


@pytest.fixture
def alices_policy_group():
    ALICE.__resource_id += b"/unique-again"  # A unique name each time, like a path.
    n = NUMBER_OF_URSULAS_IN_NETWORK

    policy_manager = PolicyManagerForAlice(ALICE)

    policy_group = policy_manager.create_policy_group(
        BOB,
        ALICE.__resource_id,
        m=3,
        n=n,
    )