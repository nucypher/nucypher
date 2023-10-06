from nucypher.blockchain.eth.domains import EthChain, PolygonChain
from nucypher.policy.conditions.evm import _CONDITION_CHAINS


def test_default_condition_chains():
    all_chains = list(EthChain) + list(PolygonChain)
    for chain in all_chains:
        assert chain.id in _CONDITION_CHAINS
