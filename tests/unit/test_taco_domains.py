import pytest

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.domains import (
    EthChain,
    PolygonChain,
)


@pytest.fixture(scope="module")
def test_registry(module_mocker):
    # override fixture which mocks domains.SUPPORTED_DOMAINS
    yield


@pytest.fixture(scope="module", autouse=True)
def mock_condition_blockchains(module_mocker):
    # override fixture which mocks domains.get_domain
    yield


@pytest.mark.parametrize(
    "eth_chain_test",
    (
        (EthChain.MAINNET, "mainnet", 1),
        (EthChain.SEPOLIA, "sepolia", 11155111),
    ),
)
def test_eth_chains(eth_chain_test):
    eth_chain, expected_name, expected_id = eth_chain_test
    assert eth_chain.name == expected_name
    assert eth_chain.id == expected_id


@pytest.mark.parametrize(
    "poly_chain_test",
    (
        (PolygonChain.MAINNET, "polygon", 137),
        (PolygonChain.AMOY, "amoy", 80002),
    ),
)
def test_polygon_chains(poly_chain_test):
    eth_chain, expected_name, expected_id = poly_chain_test
    assert eth_chain.name == expected_name
    assert eth_chain.id == expected_id


@pytest.mark.parametrize(
    "taco_domain_test",
    (
        (
            domains.MAINNET,
            "mainnet",
            EthChain.MAINNET,
            PolygonChain.MAINNET,
            (EthChain.MAINNET, PolygonChain.MAINNET),
        ),
        (
            domains.LYNX,
            "lynx",
            EthChain.SEPOLIA,
            PolygonChain.AMOY,
            (
                EthChain.MAINNET,
                EthChain.SEPOLIA,
                PolygonChain.AMOY,
                PolygonChain.MAINNET,
            ),
        ),
        (
            domains.TAPIR,
            "tapir",
            EthChain.SEPOLIA,
            PolygonChain.AMOY,
            (EthChain.SEPOLIA, PolygonChain.AMOY),
        ),
    ),
)
def test_taco_domain_info(taco_domain_test):
    (
        domain_info,
        expected_name,
        expected_eth_chain,
        expected_polygon_chain,
        expected_condition_chains,
    ) = taco_domain_test
    assert domain_info.name == expected_name
    assert domain_info.eth_chain == expected_eth_chain
    assert domain_info.polygon_chain == expected_polygon_chain
    assert domain_info.condition_chains == expected_condition_chains

    assert domain_info.is_testnet == (expected_name != "mainnet")


@pytest.mark.parametrize(
    "domain_name_test",
    (
        ("mainnet", domains.MAINNET),
        ("lynx", domains.LYNX),
        ("tapir", domains.TAPIR),
    ),
)
def test_get_domain(domain_name_test):
    domain_name, expected_domain_info = domain_name_test
    assert domains.get_domain(domain_name) == expected_domain_info


def test_get_domain_unrecognized_domain_name():
    with pytest.raises(domains.UnrecognizedTacoDomain):
        domains.get_domain("5am_In_Toronto")
