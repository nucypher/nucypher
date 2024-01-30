"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import base64
import datetime
import json
import os
import shutil
from getpass import getpass
from pathlib import Path

import maya

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.signers import Signer
from nucypher.characters.lawful import Alice, Bob
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.ethereum import connect_web3_provider
from nucypher.utilities.logging import GlobalLoggerSettings

######################
# Boring setup stuff #
######################

LOG_LEVEL = "info"
GlobalLoggerSettings.set_log_level(log_level_name=LOG_LEVEL)
GlobalLoggerSettings.start_console_logging()

TEMP_ALICE_DIR = Path("/", "tmp", "heartbeat-demo-alice")
POLICY_FILENAME = "policy-metadata.json"
shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)

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

TACO_DOMAIN = domains.LYNX


#######################################
# Alicia, the Authority of the Policy #
#######################################

connect_web3_provider(
    blockchain_endpoint=L1_PROVIDER
)  # Connect to the ethereum provider.
connect_web3_provider(
    blockchain_endpoint=L2_PROVIDER
)  # Connect to the layer 2 provider.


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

# This is Alicia.
alicia = Alice(
    checksum_address=ALICE_ADDRESS,
    signer=wallet,
    domain=TACO_DOMAIN,
    eth_endpoint=L1_PROVIDER,
    polygon_endpoint=L2_PROVIDER,
    pre_payment_method=pre_payment_method,
)

# Alice puts her public key somewhere for Bob to find later...
alice_verifying_key = alicia.stamp.as_umbral_pubkey()

# Let's get to learn about the TACo nodes on the Threshold Network
alicia.start_learning_loop(now=True)

# At this point, Alicia is fully operational and can create policies.
# The Policy Label is a bytestring that categorizes the data that Alicia wants to share.
# Note: we add some random chars to create different policies, only for demonstration purposes
label = "heart-data-❤️-" + os.urandom(4).hex()
label = label.encode()

# Alicia can create the public key associated to the policy label,
# even before creating any associated policy.
policy_pubkey = alicia.get_policy_encrypting_key_from_label(label)

print(
    "The policy public key for "
    "label '{}' is {}".format(
        label.decode("utf-8"), policy_pubkey.to_compressed_bytes().hex()
    )
)

# Data Sources can produce encrypted data for access policies
# that **don't exist yet**.
# In this example, we create a local file with encrypted data, containing
# heart rate measurements from a heart monitor
import heart_monitor  # noqa: E402

heart_monitor.generate_heart_rate_samples(policy_pubkey, samples=50, save_as_file=True)


# Alicia now wants to share data associated with this label.
# To do so, she needs the public key of the recipient.
# In this example, we generate it on the fly (for demonstration purposes)
from doctor_keys import get_doctor_pubkeys  # noqa: E402

doctor_pubkeys = get_doctor_pubkeys()

# We create a view of the Bob who's going to be granted access.
doctor_strange = Bob.from_public_keys(
    verifying_key=doctor_pubkeys["sig"], encrypting_key=doctor_pubkeys["enc"]
)

# Here are our remaining Policy details, such as:
# - Policy expiration date
policy_end_datetime = maya.now() + datetime.timedelta(days=1)
# - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
#               she requires Bob to seek collaboration of at least 3 Ursulas
threshold, shares = 2, 3


# With this information, Alicia creates a policy granting access to Bob.
# The policy is sent to the TACo Application on the Threshold Network.
print("Creating access policy for the Doctor...")
policy = alicia.grant(
    bob=doctor_strange,
    label=label,
    threshold=threshold,
    shares=shares,
    expiration=policy_end_datetime,
)
print("Done!")

# For the demo, we need a way to share with Bob some additional info
# about the policy, so we store it in a JSON file
policy_info = {
    "policy_pubkey": policy.public_key.to_compressed_bytes().hex(),
    "alice_sig_pubkey": bytes(alicia.stamp).hex(),
    "label": label.decode("utf-8"),
    "treasure_map": base64.b64encode(bytes(policy.treasure_map)).decode(),
}

filename = POLICY_FILENAME
with open(filename, "w") as f:
    json.dump(policy_info, f)
