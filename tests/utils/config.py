from typing import List

from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import (
    AliceConfiguration,
    BobConfiguration,
    UrsulaConfiguration,
)
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import select_test_port

TEST_CHARACTER_CONFIG_BASE_PARAMS = dict(
    dev_mode=True,
    domain=TEMPORARY_DOMAIN_NAME,
)


def assemble(
    eth_endpoint: str = None,
    polygon_endpoint: str = None,
    test_registry: ContractRegistry = None,
    seed_nodes: List[Ursula] = None,
) -> dict:
    """Assemble a dictionary of keyword arguments to use when constructing a test configuration."""
    middleware = MockRestMiddleware(eth_endpoint=eth_endpoint, registry=test_registry)
    runtime_params = dict(
        eth_endpoint=eth_endpoint,
        polygon_endpoint=polygon_endpoint,
        registry=test_registry,
        network_middleware=middleware,
        seed_nodes=seed_nodes,
    )

    # Combine and return
    base_test_params = dict(**TEST_CHARACTER_CONFIG_BASE_PARAMS, **runtime_params)
    return base_test_params


def make_ursula_test_configuration(port: int = select_test_port(), **assemble_kwargs) -> UrsulaConfiguration:
    test_params = assemble(**assemble_kwargs)
    ursula_config = UrsulaConfiguration(**test_params, port=port)
    return ursula_config


def make_alice_test_configuration(**assemble_kwargs) -> AliceConfiguration:
    test_params = assemble(**assemble_kwargs)
    config = AliceConfiguration(**test_params)
    return config


def make_bob_test_configuration(**assemble_kwargs) -> BobConfiguration:
    test_params = assemble(**assemble_kwargs)
    config = BobConfiguration(**test_params)
    return config
