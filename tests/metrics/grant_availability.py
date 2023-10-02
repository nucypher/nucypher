#!/usr/bin/env python3



"""
WARNING: This script makes automatic transactions.
Do not use this script unless you know what you
are doing and intend to spend ETH measuring live
policy availability.
"""

import datetime
import os
import shutil
import time
from pathlib import Path
from typing import List, Optional, Set, Tuple

import maya
from eth_typing.evm import ChecksumAddress
from nucypher_core.umbral import SecretKey
from web3 import Web3
from web3.types import Wei

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher.network.nodes import TEACHER_NODES
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.policy.policies import Policy
from nucypher.utilities.logging import GlobalLoggerSettings

# Signer Configuration
# In order to use this script, you must configure a wallet for alice
ADDRESS_ENVVAR: str = 'NUCYPHER_GRANT_METRICS_ADDRESS'
PASSWORD_ENVVAR: str = 'NUCYPHER_GRANT_METRICS_PASSWORD'
SIGNER_ENVVAR: str = 'NUCYPHER_GRANT_METRICS_KEYFILE_PATH'
PROVIDER_ENVVAR: str = 'NUCYPHER_GRANT_METRICS_PROVIDER'
POLYGON_ENVVAR: str = 'NUCYPHER_GRANT_METRICS_POLYGON_PROVIDER'

try:
    ALICE_ADDRESS: ChecksumAddress = os.environ[ADDRESS_ENVVAR]
    SIGNER_PASSWORD: str = os.environ[PASSWORD_ENVVAR]
    SIGNER_URI: str = os.environ[SIGNER_ENVVAR]
    ETHEREUM_PROVIDER_URI: str = os.environ[PROVIDER_ENVVAR]
    POLYGON_PROVIDER_URI: str = os.environ[POLYGON_ENVVAR]
except KeyError:
    message = f'{ADDRESS_ENVVAR}, ' \
              f'{PROVIDER_ENVVAR}, ' \
              f'{SIGNER_ENVVAR} and ' \
              f'{PASSWORD_ENVVAR} ' \
              f'are required to run grant availability metrics.'
    raise RuntimeError(message)

# Alice Configuration
TACO_NETWORK: str = NetworksInventory.LYNX.name  # mainnet
DEFAULT_SEEDNODE_URIS: List[str] = [
    *TEACHER_NODES[TACO_NETWORK],
]
INSECURE_PASSWORD: str = "METRICS_INSECURE_DEVELOPMENT_PASSWORD"
TEMP_ALICE_DIR: Path = Path('/', 'tmp', 'grant-metrics')

# Policy Parameters
THRESHOLD: int = 1
SHARES: int = 1
RATE: Wei = Web3.to_wei(50, 'gwei')
DURATION: datetime.timedelta = datetime.timedelta(days=1)

# Tuning
DEFAULT_ITERATIONS = None  # `None` will run forever
SAMPLE_RATE: int = 15  # seconds
GAS_STRATEGY: str = 'fast'
MAX_GAS_PRICE: int = 200  # gwei
LABEL_PREFIX = 'random-metrics-label-'
def LABEL_SUFFIXER():
    return os.urandom(16).hex()
HANDPICKED_URSULA_URIS: List[str] = [
    # DEFAULT_SEEDNODE_URIS[0],  # uncomment to use the seednode for granting
]


def make_random_bob():
    """Generates a random ephemeral Bob instance."""
    bob_verifying_secret = SecretKey.random()
    bob_verifying_key = bob_verifying_secret.public_key()
    decrypting_secret = SecretKey.random()
    decrypting_key = decrypting_secret.public_key()
    bob = Bob.from_public_keys(
        verifying_key=bob_verifying_key, encrypting_key=decrypting_key
    )
    print(f"Created BOB - {bytes(bob.stamp).hex()}")
    return bob


BOB = make_random_bob()


def metric_grant(alice, ursulas: Optional[Set[Ursula]] = None) -> Policy:
    """Perform a granting operation for metrics collection."""
    label = f'{LABEL_PREFIX}{LABEL_SUFFIXER()}'.encode()
    policy_end_datetime = maya.now() + DURATION
    policy = alice.grant(threshold=THRESHOLD,
                         shares=SHARES,
                         # ursulas=handpicked_ursulas,
                         expiration=policy_end_datetime,
                         bob=BOB,
                         label=label)
    return policy


def collect(alice: Alice,
            ursulas: Optional[Set[Ursula]] = None,
            iterations: Optional[int] = DEFAULT_ITERATIONS,
            ) -> None:
    """Collects grant success and failure rates."""
    policies, i, success, fail = dict(), 0, 0, 0
    while True:
        print(f"Attempt {i+1} of {iterations if iterations is not None else 'infinite'}")
        start = maya.now()
        try:
            policy = metric_grant(alice=alice, ursulas=ursulas)
        except Exception as e:
            fail += 1
            print(f'GRANT FAIL\n{e}')
        else:
            success += 1
            policies[policy.public_key.to_compressed_bytes().hex()] = policy  # track
            print(
                f"PEK:{policy.public_key.to_compressed_bytes().hex()} | {policy.hrac}"
            )

        # timeit
        end = maya.now()
        delta = end - start
        print(f"Completed in {(delta).total_seconds()} seconds.")

        # score
        if i+1 != iterations:
            if fail > 0:
                print(f'{fail}/{i+1} ({(fail/(i+1))*100}%) failure rate')
            if success > 0:
                print(f'{success}/{i+1} ({(success/(i+1))*100}%) success rate')
            print(f'Waiting {SAMPLE_RATE} seconds until next sample. ')
            time.sleep(SAMPLE_RATE)

        if i+1 == iterations:
            return  # exit
        else:
            i += 1  # continue


def make_alice(known_nodes: Optional[Set[Ursula]] = None):
    """Initializes a new 'persistent alice configuration' for grant metrics collection."""

    # This is Alice's PRE payment method.
    pre_payment_method = SubscriptionManagerPayment(
        network=TACO_NETWORK, blockchain_endpoint=POLYGON_PROVIDER_URI
    )

    wallet = Signer.from_signer_uri(f'keystore://{SIGNER_URI}')
    wallet.unlock_account(account=ALICE_ADDRESS, password=SIGNER_PASSWORD)

    alice_config = AliceConfiguration(
        eth_endpoint=ETHEREUM_PROVIDER_URI,
        polygon_endpoint=POLYGON_PROVIDER_URI,
        checksum_address=ALICE_ADDRESS,
        signer_uri=f'keystore://{SIGNER_URI}',
        config_root=TEMP_ALICE_DIR,
        domain=TACO_NETWORK,
        known_nodes=known_nodes,
        start_learning_now=False,
        learn_on_same_thread=True,
        gas_strategy=GAS_STRATEGY,
        max_gas_price=MAX_GAS_PRICE,
    )

    alice_config.initialize(password=INSECURE_PASSWORD)
    alice_config.keystore.unlock(password=INSECURE_PASSWORD)
    alice = alice_config.produce(pre_payment_method=pre_payment_method, signer=wallet)
    alice.start_learning_loop(now=True)
    return alice


def setup():
    """Prepares the filesystem and logger for grant metrics collection"""
    shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)
    GlobalLoggerSettings.start_console_logging()
    GlobalLoggerSettings.start_text_file_logging()
    GlobalLoggerSettings.set_log_level('info')


def aggregate_nodes(provider_uri: str) -> Tuple[Set[Ursula], Set[Ursula]]:
    """generates ursulas from URIs used in grant metrics collection"""

    seednodes = set()
    if DEFAULT_SEEDNODE_URIS:
        for uri in DEFAULT_SEEDNODE_URIS:
            ursula = Ursula.from_seed_and_stake_info(
                seed_uri=uri, eth_endpoint=provider_uri
            )
            seednodes.add(ursula)

    ursulas = set()
    if HANDPICKED_URSULA_URIS:
        for uri in HANDPICKED_URSULA_URIS:
            ursula = Ursula.from_seed_and_stake_info(
                seed_uri=uri, eth_endpoint=provider_uri
            )
            ursulas.add(ursula)

    return seednodes, ursulas


if __name__ == '__main__':
    setup()
    seednodes, ursulas = aggregate_nodes(provider_uri=ETHEREUM_PROVIDER_URI)
    alice = make_alice(known_nodes=seednodes)
    collect(alice=alice, ursulas=ursulas)
