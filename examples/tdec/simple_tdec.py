import os
from ferveo_py.ferveo_py import DkgPublicKey
from pathlib import Path

import nucypher
from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.registry import LocalContractRegistry
from nucypher.characters.lawful import Bob
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.characters.lawful import Ursula
from nucypher.utilities.logging import GlobalLoggerSettings

######################
# Boring setup stuff #
######################

LOG_LEVEL = 'info'
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

provider_uri = os.environ['DEMO_L1_PROVIDER_URI']
network = 'lynx'
here = Path(nucypher.__file__).parent
path = here / 'blockchain/eth/contract_registry/lynx/contract_registry.json'
registry = LocalContractRegistry(filepath=path)

###############
# Enrico
###############

print('--------- Threshold Encryption ---------')

coordinator_agent = CoordinatorAgent(eth_provider_uri=provider_uri, registry=registry)
ritual_id = 0  # got this from a side channel
ritual = coordinator_agent.get_ritual(ritual_id)
enrico = Enrico(encrypting_key=DkgPublicKey.from_bytes(ritual.public_key))

print(f'Fetched DKG public key {bytes(enrico.policy_pubkey).hex()} '
      f'for ritual #{ritual_id} '
      f'from Coordinator {coordinator_agent.contract.address}')

eth_balance_condition = {
    "chain": 80001,
    "method": "eth_getBalance",
    "parameters": [
        "0x210eeAC07542F815ebB6FD6689637D8cA2689392",
        "latest"
    ],
    "returnValueTest": {
        "comparator": "==",
        "value": 0
    }
}

conditions = [
    eth_balance_condition,
    # add more conditions here
]

message = 'hello world'.encode()
ciphertext = enrico.encrypt_for_dkg(
    plaintext=message,
    conditions=conditions
)

print(f'Encrypted message: {bytes(ciphertext).hex()}')

###############
# Bob
###############
print('--------- Threshold Decryption ---------')

bob = Bob(
    eth_provider_uri=provider_uri,
    domain=network,
    registry=registry,
    known_nodes=[Ursula.from_teacher_uri('https://lynx.nucypher.network:9151', min_stake=0)]
)

bob.start_learning_loop(now=True)

cleartext = bob.threshold_decrypt(
    ritual_id=ritual_id,
    ciphertext=ciphertext,
    conditions=conditions,
    # uncomment to use the precomputed variant
    # variant=FerveoVariant.PRECOMPUTED.name
)

print(bytes(cleartext).decode())
