import json
import os
import sys
import shutil
import msgpack
import maya
import traceback
from timeit import default_timer as timer

from twisted.logger import globalLogPublisher

from nucypher.characters.lawful import Bob, Ursula, Enrico
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.keystore.keypairs import DecryptingKeypair, SigningKeypair
from nucypher.network.middleware import RestMiddleware

from umbral.keys import UmbralPublicKey

from nucypher.utilities.logging import GlobalLogger
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN

GlobalLogger.set_console_logging(True)

######################
# Boring setup stuff #
######################

try:
    SEEDNODE_URI = sys.argv[1]
except IndexError:
    SEEDNODE_URI = "localhost:11500"


# TODO: path joins?
TEMP_DOCTOR_DIR = "{}/doctor-files".format(os.path.dirname(os.path.abspath(__file__)))

# Remove previous demo files and create new ones
shutil.rmtree(TEMP_DOCTOR_DIR, ignore_errors=True)

ursula = Ursula.from_seed_and_stake_info(seed_uri=SEEDNODE_URI,
                                         federated_only=True,
                                         minimum_stake=0)

# To create a Bob, we need the doctor's private keys previously generated.
from doctor_keys import get_doctor_privkeys

doctor_keys = get_doctor_privkeys()

bob_enc_keypair = DecryptingKeypair(private_key=doctor_keys["enc"])
bob_sig_keypair = SigningKeypair(private_key=doctor_keys["sig"])
enc_power = DecryptingPower(keypair=bob_enc_keypair)
sig_power = SigningPower(keypair=bob_sig_keypair)
power_ups = [enc_power, sig_power]

print("Creating the Doctor ...")

doctor = Bob(
    is_me=True,
    domains={TEMPORARY_DOMAIN},
    federated_only=True,
    crypto_power_ups=power_ups,
    start_learning_now=True,
    abort_on_learning_error=True,
    known_nodes=[ursula],
    save_metadata=False,
    network_middleware=RestMiddleware(),
)

print("Doctor = ", doctor)

# Let's join the policy generated by Alicia. We just need some info about it.
with open("policy-metadata.json", 'r') as f:
    policy_data = json.load(f)

policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["policy_pubkey"]))
alices_sig_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["alice_sig_pubkey"]))
label = policy_data["label"].encode()

print("The Doctor joins policy for label '{}'".format(label.decode("utf-8")))
doctor.join_policy(label, alices_sig_pubkey)

# Now that the Doctor joined the policy in the NuCypher network,
# he can retrieve encrypted data which he can decrypt with his private key.
# But first we need some encrypted data!
# Let's read the file produced by the heart monitor and unpack the MessageKits,
# which are the individual ciphertexts.
data = msgpack.load(open("heart_data.msgpack", "rb"), raw=False)
message_kits = (UmbralMessageKit.from_bytes(k) for k in data['kits'])

# The doctor also needs to create a view of the Data Source from its public keys
data_source = Enrico.from_public_keys(
    verifying_key=data['data_source'],
    policy_encrypting_key=policy_pubkey
)

# Now he can ask the NuCypher network to get a re-encrypted version of each MessageKit.
for message_kit in message_kits:
    try:
        start = timer()
        retrieved_plaintexts = doctor.retrieve(
            label=label,
            message_kit=message_kit,
            data_source=data_source,
            alice_verifying_key=alices_sig_pubkey
        )
        end = timer()

        plaintext = msgpack.loads(retrieved_plaintexts[0], raw=False)

        # Now we can get the heart rate and the associated timestamp,
        # generated by the heart rate monitor.
        heart_rate = plaintext['heart_rate']
        timestamp = maya.MayaDT(plaintext['timestamp'])

        # This code block simply pretty prints the heart rate info
        terminal_size = shutil.get_terminal_size().columns
        max_width = min(terminal_size, 120)
        columns = max_width - 12 - 27
        scale = columns / 40
        scaled_heart_rate = int(scale * (heart_rate - 60))
        retrieval_time = "Retrieval time: {:8.2f} ms".format(1000 * (end - start))
        line = ("-" * scaled_heart_rate) + "❤︎ ({} BPM)".format(heart_rate)
        line = line.ljust(max_width - 27, " ") + retrieval_time
        print(line)
    except Exception as e:
        # We just want to know what went wrong and continue the demo
        traceback.print_exc()
