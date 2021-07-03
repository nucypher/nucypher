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

import datetime
import sys
import json
import os
import shutil

import maya

from nucypher.characters.lawful import Bob, Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.logging import GlobalLoggerSettings


######################
# Boring setup stuff #
######################


# Twisted Logger

GlobalLoggerSettings.start_console_logging()

TEMP_ALICE_DIR = os.path.join('/', 'tmp', 'heartbeat-demo-alice')


# if your ursulas are NOT running on your current host,
# run like this: python alicia.py 172.28.1.3:11500
# otherwise the default will be fine.

try:
    SEEDNODE_URI = sys.argv[1]
except IndexError:
    SEEDNODE_URI = "localhost:11500"

POLICY_FILENAME = "policy-metadata.json"


#######################################
# Alicia, the Authority of the Policy #
#######################################


# We get a persistent Alice.
# If we had an existing Alicia in disk, let's get it from there

passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"
# If anything fails, let's create Alicia from scratch
# Remove previous demo files and create new ones

shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)

ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI,
                                         federated_only=True,
                                         minimum_stake=0)

alice_config = AliceConfiguration(
    config_root=os.path.join(TEMP_ALICE_DIR),
    domain=TEMPORARY_DOMAIN,
    known_nodes={ursula},
    start_learning_now=False,
    federated_only=True,
    learn_on_same_thread=True,
)

alice_config.initialize(password=passphrase)

alice_config.keystore.unlock(password=passphrase)
alicia = alice_config.produce()

# We will save Alicia's config to a file for later use
alice_config_file = alice_config.to_configuration_file()

# Let's get to learn about the NuCypher network
alicia.start_learning_loop(now=True)

# At this point, Alicia is fully operational and can create policies.
# The Policy Label is a bytestring that categorizes the data that Alicia wants to share.
# Note: we add some random chars to create different policies, only for demonstration purposes
label = "heart-data-❤️-"+os.urandom(4).hex()
label = label.encode()

# Alicia can create the public key associated to the policy label,
# even before creating any associated policy.
policy_pubkey = alicia.get_policy_encrypting_key_from_label(label)

print("The policy public key for "
      "label '{}' is {}".format(label.decode("utf-8"), bytes(policy_pubkey).hex()))

# Data Sources can produce encrypted data for access policies
# that **don't exist yet**.
# In this example, we create a local file with encrypted data, containing
# heart rate measurements from a heart monitor
import heart_monitor
heart_monitor.generate_heart_rate_samples(policy_pubkey,
                                          samples=50,
                                          save_as_file=True)


# Alicia now wants to share data associated with this label.
# To do so, she needs the public key of the recipient.
# In this example, we generate it on the fly (for demonstration purposes)
from doctor_keys import get_doctor_pubkeys
doctor_pubkeys = get_doctor_pubkeys()

# We create a view of the Bob who's going to be granted access.
doctor_strange = Bob.from_public_keys(verifying_key=doctor_pubkeys['sig'],
                                      encrypting_key=doctor_pubkeys['enc'],
                                      federated_only=True)

# Here are our remaining Policy details, such as:
# - Policy expiration date
policy_end_datetime = maya.now() + datetime.timedelta(days=1)
# - m-out-of-n: This means Alicia splits the re-encryption key in 5 pieces and
#               she requires Bob to seek collaboration of at least 3 Ursulas
m, n = 2, 3


# With this information, Alicia creates a policy granting access to Bob.
# The policy is sent to the NuCypher network.
print("Creating access policy for the Doctor...")
policy = alicia.grant(bob=doctor_strange,
                      label=label,
                      m=m,
                      n=n,
                      expiration=policy_end_datetime)
policy.treasure_map_publisher.block_until_complete()
print("Done!")

# For the demo, we need a way to share with Bob some additional info
# about the policy, so we store it in a JSON file
policy_info = {
    "policy_pubkey": bytes(policy.public_key).hex(),
    "alice_sig_pubkey": bytes(alicia.stamp).hex(),
    "label": label.decode("utf-8"),
}

filename = POLICY_FILENAME
with open(filename, 'w') as f:
    json.dump(policy_info, f)
