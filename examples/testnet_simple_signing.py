import base64
import json
import os
from typing import List

import requests
from hexbytes import HexBytes

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Bob
from nucypher.types import ThresholdSignatureRequest, ThresholdSignatureResponse
from nucypher.utilities.logging import GlobalLoggerSettings

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

DOMAIN = domains.LYNX

COHORT_ID = 0  # got this from a side channel
THRESHOLD = 2  # 2-of-3 signing

ETH_ENDPOINT = os.environ["DEMO_L1_PROVIDER_URI"]
POLYGON_ENDPOINT = os.environ["DEMO_L2_PROVIDER_URI"]
PORTER_BASE_URL = "https://porter-lynx.nucypher.io"


def print_signing_result(
    original_data: bytes, signature_responses: List[ThresholdSignatureResponse]
):
    print("\n-----")
    print(f"Original Message: {original_data}")

    hash_set = set([r.message_hash.hex() for r in signature_responses])
    assert len(hash_set) == 1, f"Expected one message hash, got {len(hash_set)}"
    print(f"\tMessage Hash: {list(hash_set)[0]}")
    print("\tSignatures:")
    for r in signature_responses:
        print(f"\t\t - {r.signature.hex()}")


def main():
    registry = ContractRegistry.from_latest_publication(
        domain=DOMAIN,
    )

    signing_coordinator_agent = SigningCoordinatorAgent(
        blockchain_endpoint=ETH_ENDPOINT,
        registry=registry,
    )

    data_to_sign = b"paz al amanecer"
    signing_request = ThresholdSignatureRequest(
        cohort_id=COHORT_ID,
        chain_id=signing_coordinator_agent.blockchain.client.chain_id,
        data_to_sign=data_to_sign,
        context=None,
    )

    print("--------- Threshold Signing Bob ---------")

    # known authorized encryptor for ritual 3
    bob = Bob(
        domain=DOMAIN,
        eth_endpoint=ETH_ENDPOINT,
        polygon_endpoint=POLYGON_ENDPOINT,
        registry=registry,
    )

    print(f"BOB: {bob}")
    bob.start_learning_loop(now=True)

    responses = bob.request_threshold_signatures(
        signing_request=signing_request,
    )

    print_signing_result(data_to_sign, responses)

    print("--------- Threshold Signing Porter ---------")


    response = requests.get(f"{PORTER_BASE_URL}/get_ursulas", params={"quantity": 3})
    response.raise_for_status()

    data = response.json()
    ursula_metadata = data["result"]["ursulas"]

    signing_request_b64 = base64.b64encode(bytes(signing_request)).decode()
    signing_requests = {}
    for u in ursula_metadata:
        signing_requests[u["checksum_address"]] = signing_request_b64

    params = {
        "signing_requests": signing_requests,
        "threshold": THRESHOLD,
    }

    response = requests.post(f"{PORTER_BASE_URL}/sign", json=params)
    response.raise_for_status()
    data = response.json()
    signing_results = data["result"]["signing_results"]
    errors = signing_results["errors"]
    assert len(errors) == 0, f"{errors}"  # no errors

    assert len(signing_results["signatures"]) >= THRESHOLD

    signature_responses = []
    for r in signing_results["signatures"].values():
        # Decode the base64-encoded response
        signature_response_json = json.loads(base64.b64decode(r[1]).decode())
        signature_responses.append(
            ThresholdSignatureResponse(
                message_hash=bytes(HexBytes(signature_response_json["message_hash"])),
                signature=bytes(HexBytes(signature_response_json["signature"])),
            )
        )

    print_signing_result(data_to_sign, signature_responses)


if __name__ == "__main__":
    main()
