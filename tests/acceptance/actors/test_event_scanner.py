import os

import pytest
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import ContractAgency, CoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry, GithubRegistrySource
from nucypher.utilities.events import (
    ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS,
    EventScanner,
    JSONifiedState,
)


@pytest.mark.skipif(
    os.environ.get("ALCHEMY_FREE_TIER_POLYGON_RPC_ENDPOINT", "") == "",
    reason="Alchemy Free Tier RPC not configured",
)
def test_scan_chunk_actual_alchemy_free_tier_detection():
    endpoint = os.environ["ALCHEMY_FREE_TIER_POLYGON_RPC_ENDPOINT"]
    web3 = Web3(HTTPProvider(endpoint))
    # inject poa for polygon
    web3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")

    state = JSONifiedState()
    state.restore()

    source = GithubRegistrySource(domain=domains.MAINNET)
    registry = ContractRegistry(source=source)

    coordinator_agent = ContractAgency.get_agent(
        agent_class=CoordinatorAgent,
        registry=registry,
        blockchain_endpoint=endpoint,
    )

    scanner = EventScanner(
        web3=web3,
        contract=coordinator_agent.contract,
        state=state,
        events=[],
    )

    end_block = web3.eth.block_number
    start_block = end_block - (
        ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS * 5
    )  # must be > Alchemy Free tier limit of 10
    completed_block, _ = scanner.scan_chunk(start_block, end_block)
    assert completed_block == start_block + ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS
