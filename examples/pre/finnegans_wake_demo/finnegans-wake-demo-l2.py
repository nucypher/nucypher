import datetime
import os
from getpass import getpass
from pathlib import Path

import maya

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.signers.base import Signer
from nucypher.characters.lawful import Alice, Bob
from nucypher.characters.lawful import Enrico as Enrico
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.ethereum import connect_web3_provider
from nucypher.utilities.logging import GlobalLoggerSettings

######################
# Boring setup stuff #
######################

LOG_LEVEL = "info"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

BOOK_PATH = Path("finnegans-wake-excerpt.txt")

try:
    # Replace with ethereum RPC endpoint
    L1_PROVIDER = os.environ["DEMO_L1_PROVIDER_URI"]
    L2_PROVIDER = os.environ["DEMO_L2_PROVIDER_URI"]

    # Replace with wallet filepath.
    WALLET_FILEPATH = os.environ["DEMO_L2_WALLET_FILEPATH"]
    SIGNER_URI = f"keystore://{WALLET_FILEPATH}"

    # Replace with alice's ethereum address
    ALICE_ADDRESS = os.environ["DEMO_ALICE_ADDRESS"]

except KeyError:
    raise RuntimeError("Missing environment variables to run demo.")

print("\n************** Setup **************\n")

##########
# Domain #
##########

TACO_DOMAIN = domains.LYNX

#####################
# Bob the BUIDLer  ##
#####################

# Then, there was bob. Bob learns about the
# rest of the domain from the seednode.
bob = Bob(
    domain=TACO_DOMAIN,
    eth_endpoint=L1_PROVIDER,
)

# Bob puts his public keys somewhere alice can find them.
verifying_key = bob.public_keys(SigningPower)
encrypting_key = bob.public_keys(DecryptingPower)

######################################
# Alice, the Authority of the Policy #
######################################

# Connect to the ethereum provider.
connect_web3_provider(blockchain_endpoint=L1_PROVIDER)
# Connect to the layer 2 provider.
connect_web3_provider(blockchain_endpoint=L2_PROVIDER)

# Setup and unlock alice's ethereum wallet.
# WARNING: Never give your mainnet password or mnemonic phrase to anyone.
# Do not use mainnet keys, create a dedicated software wallet to use for this demo.
wallet = Signer.from_signer_uri(SIGNER_URI)
password = os.environ.get("DEMO_ALICE_PASSWORD") or getpass(
    f"Enter password to unlock Alice's wallet ({ALICE_ADDRESS[:8]}): "
)
wallet.unlock_account(account=ALICE_ADDRESS, password=password)

# This is Alice's PRE payment method.
pre_payment_method = SubscriptionManagerPayment(
    domain=TACO_DOMAIN, blockchain_endpoint=L2_PROVIDER
)

# This is Alice.
alice = Alice(
    checksum_address=ALICE_ADDRESS,
    signer=wallet,
    domain=TACO_DOMAIN,
    eth_endpoint=L1_PROVIDER,
    polygon_endpoint=L2_PROVIDER,
    pre_payment_method=pre_payment_method,
)

# Alice puts her public key somewhere for Bob to find later...
alice_verifying_key = alice.stamp.as_umbral_pubkey()

print("\n************** Grant **************\n")

# Alice can get the policy's public key even before creating the policy.
label = b"secret/files/42"
policy_public_key = alice.get_policy_encrypting_key_from_label(label)

# From this moment on, anyone that knows the public key
# can encrypt data originally intended for Alice, but that
# can be shared with any Bob that Alice grants access.

# Alice already knows Bob's public keys from a side-channel.
remote_bob = Bob.from_public_keys(
    encrypting_key=encrypting_key,
    verifying_key=verifying_key,
    eth_endpoint=L1_PROVIDER,
)

# These are the policy details.
expiration = maya.now() + datetime.timedelta(days=1)
threshold, shares = 2, 3
price = alice.pre_payment_method.quote(expiration=expiration.epoch, shares=shares).value

# Alice grants access to Bob...
policy = alice.grant(
    remote_bob,
    label,
    threshold=threshold,
    shares=shares,
    value=price,
    expiration=expiration,
)

# ...and then disappears from the internet.
#
# Note that local characters (alice and bob), as opposed to objects representing
# remote characters constructed from public data (remote_alice and remote_bob)
# run node discovery in a background thread and must be stopped explicitly.
alice.disenchant()
del alice

#########################
# Enrico, the Encryptor #
#########################

# Now that Bob has access to the policy, let's show how Enrico the Encryptor
# can share data with the members of this Policy and then how Bob retrieves it.
with open(BOOK_PATH, "rb") as file:
    finnegans_wake = file.readlines()

print("\n************** Encrypt and Retrieve **************\n")

for counter, plaintext in enumerate(finnegans_wake):
    # Enrico knows the policy's public key from a side-channel.
    # In this demo a new enrico is being constructed for each line of text.
    # This demonstrates how many individual encryptors may encrypt for a single policy.
    # In other words -- Many data sources (Enricos) can encrypt for the policy's public key.
    enrico = Enrico(encrypting_key=policy_public_key)

    # In this case, the plaintext is a single passage from James Joyce's Finnegan's Wake.
    # The matter of whether encryption makes the passage more or less readable
    # is left to the reader to determine.
    message_kit = enrico.encrypt_for_pre(plaintext)
    del enrico

    ###############
    # Back to Bob #
    ###############

    # Now Bob can retrieve the original message by requesting re-encryption from nodes.
    cleartexts = bob.retrieve_and_decrypt(
        [message_kit],
        alice_verifying_key=alice_verifying_key,
        encrypted_treasure_map=policy.treasure_map,
    )

    # We show that indeed this is the passage originally encrypted by Enrico.
    assert plaintext == cleartexts[0]
    print(cleartexts)

bob.disenchant()
