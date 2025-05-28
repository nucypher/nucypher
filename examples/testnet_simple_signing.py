import base64
import json
import os
from typing import List

import requests
from eth_typing import ChecksumAddress
from hexbytes import HexBytes
from web3 import Web3

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Bob
from nucypher.network.signing import (
    SignatureRequest,
    SignatureRequestType,
    SignatureResponse,
)
from nucypher.policy.conditions.auth.evm import EIP1271Auth
from nucypher.utilities.logging import GlobalLoggerSettings

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

DOMAIN = domains.LYNX

COHORT_ID = 1  # got this from a side channel
THRESHOLD = 2  # 2-of-3 signing

ERC_1271_ABI = """[
    {
        "constant":true,
        "inputs":[
            {
                "name":"_hash",
                "type":"bytes32"
            },
            {
                "name":"_signature",
                "type":"bytes"
            }
        ],
        "name":"isValidSignature",
        "outputs":[
            {
                "name":"magicValue",
                "type":"bytes4"
            }
        ],
        "payable":false,
        "stateMutability":"view",
        "type":"function"
    }
]"""

ETH_ENDPOINT = os.environ["DEMO_L1_PROVIDER_URI"]
POLYGON_ENDPOINT = os.environ["DEMO_L2_PROVIDER_URI"]
PORTER_BASE_URL = "https://porter-lynx.nucypher.io"


def get_eth_multisig_address(
    signing_coordinator_agent: SigningCoordinatorAgent,
) -> ChecksumAddress:
    abi = """[
        {
            "type":"function",
            "name":"cohortMultisigs",
            "stateMutability":"view",
            "inputs":[
                {
                    "name":"",
                    "type":"uint32",
                    "internalType":"uint32"
                }
            ],
            "outputs":[
                {
                    "name":"",
                    "type":"address",
                    "internalType":"address"
                }
            ]
        }
    ]"""
    w3 = Web3(Web3.HTTPProvider(ETH_ENDPOINT))
    signing_coordinator_child_eth = w3.eth.contract(
        signing_coordinator_agent.get_signing_coordinator_child(DOMAIN.eth_chain.id),
        abi=abi,
    )
    multisig_address = signing_coordinator_child_eth.functions.cohortMultisigs(
        COHORT_ID
    ).call()
    return multisig_address


def validate_responses_with_cohort_eth_multisig(
    signing_coordinator_agent: SigningCoordinatorAgent,
    responses: List[SignatureResponse],
):
    w3 = signing_coordinator_agent.blockchain.client.w3
    multisig_address = get_eth_multisig_address(signing_coordinator_agent)
    er1271_contract = w3.eth.contract(address=multisig_address, abi=ERC_1271_ABI)
    assert (
        er1271_contract.functions.isValidSignature(
            responses[0].message_hash, b"".join([r.signature for r in responses])
        ).call()
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )
    print(
        f"✓ Signatures validated by multisig contract on ETH-Sepolia: {multisig_address}"
    )


def print_signing_result(
    original_data: bytes, signature_responses: List[SignatureResponse]
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
    signing_request = SignatureRequest(
        cohort_id=COHORT_ID,
        chain_id=signing_coordinator_agent.blockchain.client.chain_id,
        data=data_to_sign,
        context=None,
        signature_type=SignatureRequestType.EIP_191,
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
    validate_responses_with_cohort_eth_multisig(signing_coordinator_agent, responses)

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
            SignatureResponse(
                message=data_to_sign,
                _hash=bytes(HexBytes(signature_response_json["message_hash"])),
                signature=bytes(HexBytes(signature_response_json["signature"])),
            )
        )

    print_signing_result(data_to_sign, signature_responses)
    validate_responses_with_cohort_eth_multisig(signing_coordinator_agent, responses)


if __name__ == "__main__":
    main()
