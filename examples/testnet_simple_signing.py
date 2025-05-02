import base64
import os

import requests

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Bob
from nucypher.types import ThresholdSignatureRequest
from nucypher.utilities.logging import GlobalLoggerSettings

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

domain = domains.LYNX

cohort_id = 0  # got this from a side channel
threshold = 2

data_to_sign = b"paz al amanecer"
signing_request = ThresholdSignatureRequest(
    cohort_id=cohort_id,
    data_to_sign=data_to_sign,
    context=None,
)

print("--------- Threshold Signing Bob ---------")

eth_endpoint = os.environ["DEMO_L1_PROVIDER_URI"]
polygon_endpoint = os.environ["DEMO_L2_PROVIDER_URI"]

registry = ContractRegistry.from_latest_publication(
    domain=domain,
)

signing_coordinator_agent = SigningCoordinatorAgent(
    blockchain_endpoint=polygon_endpoint,
    registry=registry,
)

# known authorized encryptor for ritual 3
bob = Bob(
    domain=domain,
    eth_endpoint=eth_endpoint,
    polygon_endpoint=polygon_endpoint,
    registry=registry,
)

print(f"BOB: {bob}")
bob.start_learning_loop(now=True)

signatures = bob.request_threshold_signatures(
    signing_request=signing_request,
)

print(f"\nSignatures:\n{signatures}")

print("--------- Threshold Signing Porter ---------")

porter_base_url = "http://127.0.0.1:9155"
response = requests.get(f"{porter_base_url}/get_ursulas", params={"quantity": 3})
response.raise_for_status()

data = response.json()
ursula_metadata = data["result"]["ursulas"]

signing_request_b64 = base64.b64encode(bytes(signing_request)).decode()
signing_requests = {}
for u in ursula_metadata:
    signing_requests[u["checksum_address"]] = signing_request_b64

params = {
    "signing_requests": signing_requests,
    "threshold": threshold,
}

response = requests.post(f"{porter_base_url}/sign", json=params)
response.raise_for_status()
data = response.json()
signing_results = data["result"]["signing_results"]
errors = signing_results["errors"]
assert len(errors) == 0, f"{errors}"  # no errors

assert len(signing_results["signatures"]) >= threshold

print(
    f"\nSignatures:\n{[base64.b64decode(s[1]) for s in signing_results['signatures'].values()]}"
)
