import json
import os
import shutil
import pickle
import maya
from timeit import default_timer as timer
from requests.exceptions import SSLError
from urllib.parse import urlparse

from nucypher.characters.lawful import Bob, Ursula
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import EncryptingPower, SigningPower
from nucypher.data_sources import DataSource
from nucypher.keystore.keypairs import EncryptingKeypair, SigningKeypair
from nucypher.network.middleware import RestMiddleware

from umbral.keys import UmbralPublicKey

from doctor_keys import get_doctor_privkeys
import heart_monitor


with open("policy.json", 'r') as f:
    policy_data = json.load(f)

policy_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["policy_pubkey"]))
alices_sig_pubkey = UmbralPublicKey.from_bytes(bytes.fromhex(policy_data["alice_sig_pubkey"]))
label = policy_data["label"].encode()

SEEDNODE_URL = "SEEDNODE URL ..."

# TODO: path joins?
TEMP_DOCTOR_DIR = "{}/doctor-files".format(os.path.dirname(os.path.abspath(__file__)))

TEMP_URSULA_CERTIFICATE_DIR = "{}/ursula-certs".format(TEMP_DOCTOR_DIR)
TEMP_DOCTOR_CERTIFICATE_DIR = "{}/doctor-certs".format(TEMP_DOCTOR_DIR)

# Remove previous demo files and create new ones
shutil.rmtree(TEMP_DOCTOR_DIR, ignore_errors=True)
os.mkdir(TEMP_DOCTOR_DIR)
os.mkdir(TEMP_URSULA_CERTIFICATE_DIR)
os.mkdir(TEMP_DOCTOR_CERTIFICATE_DIR)

ursula = Ursula.from_seed_and_stake_info(host=SEEDNODE_URL,
                                         certificates_directory=TEMP_URSULA_CERTIFICATE_DIR,
                                         federated_only=True,
                                         minimum_stake=0)

print("Ursula: ", ursula)


doctor_keys = get_doctor_privkeys()

bob_enc_keypair = EncryptingKeypair(private_key=doctor_keys["enc"])
bob_sig_keypair = SigningKeypair(private_key=doctor_keys["sig"])

enc_power = EncryptingPower(keypair=bob_enc_keypair)
sig_power = SigningPower(keypair=bob_sig_keypair)

power_ups = [enc_power, sig_power]

print("Creating Bob ...")

bob = Bob(
    is_me=True,
    federated_only=True,
    crypto_power_ups=power_ups,
    start_learning_now=True,
    known_certificates_dir=TEMP_DOCTOR_CERTIFICATE_DIR,
    abort_on_learning_error=True,
    known_nodes=[ursula],
    save_metadata=False,
    network_middleware=RestMiddleware(),
)

print("Bob = ", bob)

print("Bob joins policy for label ", label)
bob.join_policy(label, alices_sig_pubkey)


# data = heart_monitor.generate_heart_rate_samples(policy_pubkey,
#                                           label=label,
#                                           save_as_file=False)

data = pickle.load(open(heart_monitor.HEART_DATA_FILENAME, "rb"))

data_source = DataSource.from_public_keys(
        policy_public_key=policy_pubkey,
        datasource_public_key=data['data_source'],
        label=label
    )

kits = (UmbralMessageKit.from_bytes(k) for k in data['kits'])

for message_kit in kits:

    try:
        #print("Bob retrieves ...")
        start = timer()
        delivered_cleartexts = bob.retrieve(message_kit=message_kit,
                                            data_source=data_source,
                                            alice_verifying_key=alices_sig_pubkey
                                            )
    except SSLError as e:
        node_ip = urlparse(e.request.url).hostname
        print(">> Connection problem with node ", node_ip)
    else:
        end = timer()

        plaintext = pickle.loads(delivered_cleartexts[0])

        heart_rate = plaintext['heart_rate']
        _timestamp = maya.MayaDT(plaintext['timestamp'])

        terminal_size = shutil.get_terminal_size().columns
        max_width = min(terminal_size, 120)
        columns = max_width - 10 - 27
        scale = columns/40
        scaled_heart_rate = int(scale * (heart_rate - 60))
        retrieval_time = "Retrieval time: {:8.2f} ms".format(1000*(end - start))
        line = "* ({} BPM)".rjust(scaled_heart_rate, " ")
        line = line.format(heart_rate)
        line = line.ljust(max_width - 27, " ") + retrieval_time

        print(line)