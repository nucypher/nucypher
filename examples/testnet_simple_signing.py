import os

import requests
from nucypher_core.ferveo import DkgPublicKey

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import CoordinatorAgent, SigningCoordinatorAgent
from nucypher.blockchain.eth.domains import PolygonChain
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.characters.lawful import Bob, Enrico, Ursula
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType
from nucypher.utilities.logging import GlobalLoggerSettings
from nucypher.utilities.profiler import Profiler
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

eth_endpoint = os.environ["DEMO_L1_PROVIDER_URI"]
domain = domains.LYNX

polygon_endpoint = os.environ["DEMO_L2_PROVIDER_URI"]


print("--------- Threshold Signing ---------")

registry = ContractRegistry.from_latest_publication(
    domain=domain,
)

coordinator_agent = SigningCoordinatorAgent(
    blockchain_endpoint=polygon_endpoint,
    registry=registry,
)
cohort_id = 1  # got this from a side channel
ritual = coordinator_agent.get_signing_cohort(cohort_id)

# known authorized encryptor for ritual 3
bob = Bob(
    domain=domain,
    eth_endpoint=eth_endpoint,
    polygon_endpoint=polygon_endpoint,
    registry=registry,
)

print(f"BOB: {bob}")


time_condition = {
    "version": ConditionLingo.VERSION,
    "condition": {
        "conditionType": ConditionType.TIME.value,
        "chain": 80002,
        "method": "blocktime",
        "returnValueTest": {"comparator": ">", "value": 0},
    },
}

bob.start_learning_loop(now=True)

porter_url = "http://127.0.0.1:9155/get_ursulas"
result = requests.get(porter_url, params={"quantity": 3})
ursula_metadata = result.json()["result"]["ursulas"]

ursulas = []
for u in ursula_metadata:
    ursula = Ursula.from_teacher_uri(u["uri"], eth_endpoint=eth_endpoint, min_stake=0)
    ursulas.append(ursula)

data_to_sign = b"paz al amanecer"

signatures = bob.request_threshold_signatures(
    data_to_sign=data_to_sign,
    cohort_id=cohort_id,
    threshold=2,
    conditions=time_condition,
    timeout=60,
    ursulas=ursulas,
)

print(f"\nSignatures:\n{signatures}")
