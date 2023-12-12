import pprint
import random
from collections import defaultdict

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import (
    ContractAgency,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.blockchain.eth.registry import ContractRegistry

domain = "mainnet"
infura_id = "..."
polygon_endpoint = "https://polygon-mainnet.infura.io/v3/" + infura_id
eth_endpoint = "https://mainnet.infura.io/v3/" + infura_id
dkg_size = 30
# adopter_seed = 42
# random.seed(adopter_seed)
unlocking_delay = 182 * 24 * 60 * 60

domain = domains.get_domain(domain)
registry = ContractRegistry.from_latest_publication(domain=domain)

child_application_agent = ContractAgency.get_agent(
    agent_class=TACoChildApplicationAgent,
    registry=registry,
    blockchain_endpoint=polygon_endpoint,
)

taco_application_agent = ContractAgency.get_agent(
    agent_class=TACoApplicationAgent,
    registry=registry,
    blockchain_endpoint=eth_endpoint,
)

# _, staking_providers_dict = child_application_agent.get_all_active_staking_providers()
# staking_providers = list(staking_providers_dict.keys())


def horizon(info: TACoApplicationAgent.StakingProviderInfo):
    amount = info.authorized - info.deauthorizing
    if amount < 40_000 * 10**18:
        return 0


# TODO: Use multicall
# staking_providers_info = [taco_application_agent.get_staking_provider_info(s) for s in staking_providers]
# pprint.pp(staking_providers_info)
# staking_horizons = {s: horizon(staking_providers_info[s]) for s in staking_providers}

population = list(range(55))

max_from_bucket = 2


def find_node_in_bucket(node):
    buckets = {
        "nuco": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        "dao": [10, 11, 12, 13, 14, 15],
        "provider1": [16, 17, 18, 19, 20],
        "provider2": [21, 22, 23, 24, 25],
        "provider3": [26, 27, 28, 29, 30],
        "keep": [31, 32, 33, 34],
        "adopter1": [35, 36],
        "adopter2": [37, 38],
    }
    for bucket_name, bucket_nodes in buckets.items():
        if node in bucket_nodes:
            return bucket_name
    return "no_bucket"


for i in range(20):
    tries = 0
    sample = defaultdict(list)
    staking_providers = list(population)
    while sum(map(len, sample.values())) < dkg_size:
        if not staking_providers:
            break
        selected = random.choice(staking_providers)
        tries += 1
        staking_providers.remove(selected)
        bucket = find_node_in_bucket(selected)
        if (
            bucket in sample
            and bucket != "no_bucket"
            and len(sample[bucket]) >= max_from_bucket
        ):
            continue
        sample[bucket].append(selected)

    success = sum(map(len, sample.values())) == dkg_size

    print(
        f"Sampling #{i}: {'GREAT SUCCESS' if success else 'FAILED'} – required {tries} tries"
    )
    pprint.pp(dict(sample))
