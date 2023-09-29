from typing import List

from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import (
    AliceConfiguration,
    BobConfiguration,
    UrsulaConfiguration,
)
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import select_test_port

TEST_CHARACTER_CONFIG_BASE_PARAMS = dict(
    dev_mode=True,
    domain=TEMPORARY_DOMAIN,
    start_learning_now=False,
    abort_on_learning_error=True,
    save_metadata=False,
    reload_metadata=False
)


def assemble(
    checksum_address: str = None,
    eth_endpoint: str = None,
    test_registry: ContractRegistry = None,
    known_nodes: List[Ursula] = None,
) -> dict:
    """Assemble a dictionary of keyword arguments to use when constructing a test configuration."""
    # Generate runtime config params
    runtime_params = dict(
        eth_endpoint=eth_endpoint,
        registry=test_registry,
        network_middleware=MockRestMiddleware(eth_provider_uri=eth_endpoint),
        known_nodes=known_nodes,
        checksum_address=checksum_address,
    )

    # Combine and return
    base_test_params = dict(**TEST_CHARACTER_CONFIG_BASE_PARAMS, **runtime_params)
    return base_test_params


def make_ursula_test_configuration(
    operator_address: ChecksumAddress,
    rest_port: int = select_test_port(),
    polygon_endpoint: str = None,
    **assemble_kwargs
) -> UrsulaConfiguration:
    test_params = assemble(**assemble_kwargs)
    ursula_config = UrsulaConfiguration(
        **test_params,
        rest_port=rest_port,
        polygon_endpoint=polygon_endpoint,
        pre_payment_network=TEMPORARY_DOMAIN,
        operator_address=operator_address,
        policy_registry=test_params["registry"]
    )
    return ursula_config


def make_alice_test_configuration(
    polygon_endpoint: str = None, **assemble_kwargs
) -> AliceConfiguration:
    test_params = assemble(**assemble_kwargs)
    config = AliceConfiguration(
        **test_params,
        polygon_endpoint=polygon_endpoint,
        pre_payment_network=TEMPORARY_DOMAIN,
        policy_registry=test_params["registry"]
    )
    return config


def make_bob_test_configuration(**assemble_kwargs) -> BobConfiguration:
    test_params = assemble(**assemble_kwargs)
    config = BobConfiguration(**test_params)
    return config
