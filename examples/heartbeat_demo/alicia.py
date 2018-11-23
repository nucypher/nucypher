from nucypher.characters.lawful import Bob, Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.crypto.powers import EncryptingPower, SigningPower
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import simpleObserver
from umbral.keys import UmbralPublicKey

from doctor_keys import get_doctor_pubkeys

import datetime
import os
import shutil
import maya
import json
from twisted.logger import globalLogPublisher


POLICY_FILENAME = "policy.json"


######################
# Boring setup stuff #
######################
#
# # Twisted Logger
globalLogPublisher.addObserver(simpleObserver)
#
# # Temporary file storage
TEMP_ALICE_DIR = "{}/alicia-files".format(os.path.dirname(os.path.abspath(__file__)))
TEMP_URSULA_CERTIFICATE_DIR = "{}/ursula-certs".format(TEMP_ALICE_DIR)


SEEDNODE_URL = "SEEDNODE URL ..."


# Here are our Policy details.
policy_end_datetime = maya.now() + datetime.timedelta(days=5)
m, n = 3, 5
label = b"label-"+os.urandom(4).hex().encode()

######################################
# Alice, the Authority of the Policy #
######################################


passphrase = "TEST_ALICIA_INSECURE_DEVELOPMENT_PASSWORD"


try:  # If we had an existing Alicia in disk, let's get it from there
    alice_config_file = os.path.join(TEMP_ALICE_DIR, "config_root", "alice.config")
    new_alice_config = AliceConfiguration.from_configuration_file(
            filepath=alice_config_file,
            network_middleware=RestMiddleware(),
            #known_nodes={ursula},
            start_learning_now=False,
            save_metadata=False,
        )
    alicia = new_alice_config(passphrase=passphrase)
except:  # If anything fails, let's create Alicia from scratch
    # Remove previous demo files and create new ones
    shutil.rmtree(TEMP_ALICE_DIR, ignore_errors=True)
    os.mkdir(TEMP_ALICE_DIR)
    os.mkdir(TEMP_URSULA_CERTIFICATE_DIR)

    ursula = Ursula.from_seed_and_stake_info(host=SEEDNODE_URL,
                                             certificates_directory=TEMP_URSULA_CERTIFICATE_DIR,
                                             federated_only=True,
                                             minimum_stake=0)


    # Let's create an Alice from a Configuration.
    # This requires creating a local storage for her first.
    node_storage = LocalFileBasedNodeStorage(
        federated_only=True,
        character_class=Ursula,  # Alice needs to store some info about Ursula
        known_metadata_dir=os.path.join(TEMP_ALICE_DIR, "known_metadata"),
    )

    alice_config = AliceConfiguration(
        config_root=os.path.join(TEMP_ALICE_DIR, "config_root"),
        node_storage=node_storage,
        auto_initialize=True,
        auto_generate_keys=True,
        passphrase=passphrase,
        is_me=True,
        known_nodes={ursula},
        start_learning_now=False,
        federated_only=True,
        #save_metadata=False,
        #load_metadata=False,
        learn_on_same_thread=True,
    )
    alicia = alice_config(passphrase=passphrase,
                          known_certificates_dir=TEMP_URSULA_CERTIFICATE_DIR,
                          )

    # We will save Alice's config to a file for later use
    alice_config_file = alice_config.to_configuration_file()
    #print(alice_config_file)


# Alicia can create the public key associated to the label,
# even before creating any policy.
policy_pubkey = alicia.get_policy_pubkey_from_label(label)

# This illustrates that Data Sources can produce encrypted data for policies
# that **don't exist yet**.
import heart_monitor
heart_monitor.generate_heart_rate_samples(policy_pubkey,
                                          label=label,
                                          save_as_file=True)


doctor_pubkeys = get_doctor_pubkeys()

print("doctor_pubkeys", doctor_pubkeys)

powers_and_material = {EncryptingPower: doctor_pubkeys['enc'],
                       SigningPower: doctor_pubkeys['sig']}

doctor_strange = Bob.from_public_keys(powers_and_material=powers_and_material,
                                      federated_only=True)

alicia.start_learning_loop(now=True)

policy = alicia.grant(bob=doctor_strange,
                      label=label,
                      m=m,
                      n=n,
                      expiration=policy_end_datetime)

policy_info = {
    "policy_pubkey": policy.public_key.to_bytes().hex(),
    "alice_sig_pubkey": bytes(alicia.stamp).hex(),
    "label": label.decode("utf-8"),
}

filename = POLICY_FILENAME
with open(filename, 'w') as f:
    json.dump(policy_info, f)

