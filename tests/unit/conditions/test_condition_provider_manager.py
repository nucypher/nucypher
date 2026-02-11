from unittest.mock import patch

import pytest

from nucypher.policy.conditions.exceptions import (
    NoConnectionToChain,
)
from nucypher.policy.conditions.utils import (
    ConditionProviderManager,
)
from nucypher.utilities.endpoint import RPCEndpoint


def test_no_connection_to_chain(mocker):
    # no condition to chain
    with pytest.raises(NoConnectionToChain, match="No connection to chain ID"):
        manager = ConditionProviderManager(providers={2: ["https://provider.test"]})
        _ = manager.exec_web3_call(chain_id=1, fn=lambda w3: None)


def test_multiple_providers(mocker):
    # multiple providers
    provider_manager = ConditionProviderManager(
        providers={2: ["https://provider1.test", "https://provider2.test"]}
    )

    w3_instances = []

    def collect_w3_instances(w3):
        w3_instances.append(w3)
        raise Exception(
            "raise exception to cause endpoint manager to try next provider"
        )

    with pytest.raises(Exception):
        provider_manager.exec_web3_call(chain_id=2, fn=collect_w3_instances)
    assert len(w3_instances) == 2
    for w3_instance in w3_instances:
        assert w3_instance  # actual object returned
        assert w3_instance.middleware_onion.get("poa")  # poa middleware injected

    # specific w3 instances
    w3_1 = mocker.Mock()
    w3_1.eth.chain_id = 2
    w3_2 = mocker.Mock()
    w3_2.eth.chain_id = 2
    w3_instances.clear()
    with patch.object(RPCEndpoint, "_configure_w3", side_effect=[w3_1, w3_2]):
        with pytest.raises(Exception):
            provider_manager.exec_web3_call(chain_id=2, fn=collect_w3_instances)

        assert w3_instances == [w3_1, w3_2]


# TODO Move / Fix tests.

# def test_preferential_provider_ordering():
#     # preferential provider
#     preferential_providers = [f"https://pref.provider.{i}.test" for i in range(3)]
#     other_providers = [f"https://other.provider.{i}.test" for i in range(2)]
#     chain_3_providers = [f"https://chain3.provider.{i}.test" for i in range(2)]
#     manager = ConditionProviderManager(
#         providers={2: other_providers, 3: chain_3_providers},
#         preferential_providers={2: preferential_providers},
#     )
#
#
#     w3_instances = list(manager.web3_endpoints(chain_id=2))
#     assert len(w3_instances) == (len(preferential_providers) + len(other_providers))
#
#     # preferential is first and order maintained
#     for i, w3_instance in enumerate(w3_instances[: len(preferential_providers)]):
#         assert w3_instance.provider.endpoint_uri == preferential_providers[i]
#
#     # other providers follow in random order
#     for w3_instance in w3_instances[len(preferential_providers) :]:
#         assert w3_instance.provider.endpoint_uri in other_providers
#
#     chain_3_w3_instances = list(manager.web3_endpoints(chain_id=3))
#     assert len(chain_3_w3_instances) == len(chain_3_providers)
#     for w3_instance in chain_3_w3_instances:
#         assert w3_instance.provider.endpoint_uri in chain_3_providers
#
#
# def test_provider_randomization():
#     # order randomized
#     all_providers = [f"https://provider.{i}.test" for i in range(10)]
#     manager = ConditionProviderManager(providers={2: all_providers})
#     num_times_different = 0
#     for i in range(5):
#         w3_instances_first = list(manager.web3_endpoints(chain_id=2))
#         w3_instances_second = list(manager.web3_endpoints(chain_id=2))
#         if any(
#             w31.provider.endpoint_uri != w32.provider.endpoint_uri
#             for w31, w32 in zip(w3_instances_first, w3_instances_second)
#         ):
#             num_times_different += 1
#     assert num_times_different > 0  # at least one time the order differed
