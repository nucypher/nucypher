"""
Example demonstrating threshold signing using UserOperation requests.
The /sign endpoint now supports UserOperation and PackedUserOperation signature requests
for account abstraction use cases.

NOTE: This example requires:
1. An active signing cohort on the network (check COHORT_ID)
2. A configured signing condition for the cohort
3. Proper authorization to request signatures

Without these prerequisites, the signing requests will fail with appropriate error messages.
"""

import base64
import os
from typing import List

import requests
from eth_typing import ChecksumAddress
from nucypher_core import (
    AAVersion,
    EncryptedThresholdSignatureResponse,
    SessionStaticKey,
    SessionStaticSecret,
    SignatureResponse,
    UserOperation,
    UserOperationSignatureRequest,
)
from web3 import Web3

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import SigningCoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Bob
from nucypher.policy.conditions.auth.evm import EIP1271Auth
from nucypher.utilities.logging import GlobalLoggerSettings

LOG_LEVEL = "debug"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

DOMAIN = domains.LYNX

# You need to know the cohort ID of an active signing cohort
# This can be obtained from the SigningCoordinator contract events or other sources
COHORT_ID = 1  # Update this to match an actual active cohort ID
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

ETH_ENDPOINT = os.environ.get("DEMO_L1_PROVIDER_URI", "https://sepolia.drpc.org")
POLYGON_ENDPOINT = os.environ.get(
    "DEMO_L2_PROVIDER_URI", "https://polygon-amoy.drpc.org"
)
PORTER_BASE_URL = f"https://porter-{DOMAIN.name}.nucypher.io"


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
            responses[0].hash, b"".join([r.signature for r in responses])
        ).call()
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )
    print(
        f"✓ Signatures validated by multisig contract on ETH-Sepolia: {multisig_address}"
    )


def print_signing_result(
    user_op: UserOperation, signature_responses: List[SignatureResponse]
):
    print("\n-----")
    print(f"UserOperation sender: {user_op.sender}")
    print(f"UserOperation nonce : {user_op.nonce}")

    hash_set = set([r.hash.hex() for r in signature_responses])
    assert len(hash_set) == 1, f"Expected one message hash, got {len(hash_set)}"
    print(f"\tMessage Hash: {list(hash_set)[0]}")
    print("\tSignatures:")
    for r in signature_responses:
        print(f"\t\t - {r.signature.hex()}")


def create_sample_user_operation() -> UserOperation:
    """Create a sample UserOperation for demonstration purposes."""
    # This is a sample UserOperation for an ETH transfer
    # In a real scenario, you would construct this based on your specific needs
    return UserOperation(
        sender="0x1234567890123456789012345678901234567890",  # Example address
        nonce=1,
        call_data=b"",  # Empty for simple ETH transfer
        call_gas_limit=100000,
        verification_gas_limit=100000,
        pre_verification_gas=21000,
        max_fee_per_gas=2000000000,
        max_priority_fee_per_gas=1000000000,
    )


def main():
    registry = ContractRegistry.from_latest_publication(
        domain=DOMAIN,
    )

    signing_coordinator_agent = SigningCoordinatorAgent(
        blockchain_endpoint=ETH_ENDPOINT,
        registry=registry,
    )

    # Create a UserOperation to sign
    user_op = create_sample_user_operation()

    # Create signing request
    signing_request = UserOperationSignatureRequest(
        user_op=user_op,
        cohort_id=COHORT_ID,
        chain_id=signing_coordinator_agent.blockchain.client.chain_id,
        aa_version=AAVersion.V08,  # Using AA version 0.8
        context=None,
    )

    print("--------- Threshold Signing Bob ---------")

    bob = Bob(
        domain=DOMAIN,
        eth_endpoint=ETH_ENDPOINT,
        polygon_endpoint=POLYGON_ENDPOINT,
        registry=registry,
    )

    print(f"BOB: {bob}")
    bob.start_learning_loop(now=True)

    try:
        responses = bob.request_threshold_signatures(
            signing_request=signing_request,
        )

        print_signing_result(user_op, responses)
        validate_responses_with_cohort_eth_multisig(
            signing_coordinator_agent, responses
        )
    except Exception as e:
        print(f"Signing failed: {e}")
        print("Note: This may fail if no condition is configured for the cohort")

    print("\n--------- Threshold Signing Porter ---------")

    # e2e communication
    requester_sk = SessionStaticSecret.random()
    requester_pk = requester_sk.public_key()

    signing_cohort = signing_coordinator_agent.get_signing_cohort(COHORT_ID)
    signers_info = {
        s.provider: SessionStaticKey.from_bytes(s.signing_request_key)
        for s in signing_cohort.signers
    }

    response = requests.get(f"{PORTER_BASE_URL}/get_ursulas", params={"quantity": 3})
    response.raise_for_status()

    data = response.json()
    ursula_metadata = data["result"]["ursulas"]

    encrypted_signing_requests = {}
    shared_secrets = {}
    for u in ursula_metadata:
        ursula_checksum_address = u["checksum_address"]
        # Derive shared secret
        shared_secret = requester_sk.derive_shared_secret(
            signers_info[ursula_checksum_address]
        )
        shared_secrets[ursula_checksum_address] = shared_secret
        # Create encrypted signing request
        encrypted_request = signing_request.encrypt(
            shared_secret=shared_secret, requester_public_key=requester_pk
        )
        encrypted_signing_requests[ursula_checksum_address] = base64.b64encode(
            bytes(encrypted_request)
        ).decode()

    params = {
        "encrypted_signing_requests": encrypted_signing_requests,
        "threshold": THRESHOLD,
    }

    try:
        response = requests.post(f"{PORTER_BASE_URL}/sign", json=params)
        response.raise_for_status()
        data = response.json()
        signing_results = data["result"]["signing_results"]
        errors = signing_results["errors"]

        if len(errors) > 0:
            print(f"Signing errors: {errors}")

        encrypted_signature_responses = signing_results["encrypted_signature_responses"]
        if len(encrypted_signature_responses) >= THRESHOLD:
            signature_responses = []
            for (
                ursula_address,
                encrypted_response,
            ) in encrypted_signature_responses.items():
                # Decode the base64-encoded response
                encrypted_response = EncryptedThresholdSignatureResponse.from_bytes(
                    base64.b64decode(encrypted_response)
                )
                signature_response = encrypted_response.decrypt(
                    shared_secret=shared_secrets[ursula_address]
                )
                signature_responses.append(signature_response)

            # sort signature responses by signer
            signature_responses = sorted(
                signature_responses, key=lambda r: int(r.signer, 16)
            )
            print_signing_result(user_op, signature_responses)
            validate_responses_with_cohort_eth_multisig(
                signing_coordinator_agent, signature_responses
            )
        else:
            print(
                f"Not enough signatures: {len(signing_results['signatures'])} < {THRESHOLD}"
            )
    except Exception as e:
        print(f"Porter signing failed: {e}")
        print("Note: This may fail if no condition is configured for the cohort")


if __name__ == "__main__":
    main()
