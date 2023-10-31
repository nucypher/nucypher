import os
from nucypher_core.ferveo import DkgPublicKey

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.characters.lawful import Bob, Enrico
from nucypher.policy.conditions.lingo import ConditionLingo, ConditionType
from nucypher.utilities.logging import GlobalLoggerSettings
from nucypher.utilities.profiler import Profiler
from tests.constants import DEFAULT_TEST_ENRICO_PRIVATE_KEY

######################
# Boring setup stuff #
######################

LOG_LEVEL = "info"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

eth_endpoint = os.environ["DEMO_L1_PROVIDER_URI"]
domain = domains.LYNX

polygon_endpoint = os.environ["DEMO_L2_PROVIDER_URI"]

###############
# Enrico
###############

print("--------- Threshold Encryption ---------")

registry = ContractRegistry.from_latest_publication(
    domain=domain,
)

coordinator_agent = CoordinatorAgent(
    blockchain_endpoint=polygon_endpoint,
    registry=registry,
)
ritual_id = 3  # got this from a side channel
ritual = coordinator_agent.get_ritual(ritual_id)

# known authorized encryptor for ritual 3
signer = InMemorySigner(private_key=DEFAULT_TEST_ENRICO_PRIVATE_KEY)
enrico = Enrico(
    encrypting_key=DkgPublicKey.from_bytes(bytes(ritual.public_key)), signer=signer
)

print(
    f"Fetched DKG public key {bytes(enrico.policy_pubkey).hex()} "
    f"for ritual #{ritual_id} "
    f"from Coordinator {coordinator_agent.contract.address}"
)

eth_balance_condition = {
    "version": ConditionLingo.VERSION,
    "condition": {
        "conditionType": ConditionType.RPC.value,
        "chain": 80001,
        "method": "eth_getBalance",
        "parameters": ["0x210eeAC07542F815ebB6FD6689637D8cA2689392", "latest"],
        "returnValueTest": {"comparator": "==", "value": 0},
    },
}

message = "hello world".encode()
threshold_message_kit = enrico.encrypt_for_dkg(
    plaintext=message, conditions=eth_balance_condition
)

print(f"\nEncrypted message:\n{bytes(threshold_message_kit).hex()}")

###############
# Bob
###############
print("--------- Threshold Decryption ---------")

bob = Bob(
    domain=domain,
    eth_endpoint=eth_endpoint,
    polygon_endpoint=polygon_endpoint,
    registry=registry,
)

bob.start_learning_loop(now=True)

with Profiler():
    cleartext = bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )

    cleartext = bytes(cleartext)
    print(f"\nCleartext: {cleartext.decode()}")
    assert message == cleartext
