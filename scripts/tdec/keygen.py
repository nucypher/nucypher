import json

from nucypher_core.umbral import SecretKey

from nucypher.characters.lawful import Bob, Alice, Ursula
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.logging import GlobalLoggerSettings

GlobalLoggerSettings.set_log_level(log_level_name='info')
GlobalLoggerSettings.start_console_logging()

# Universal Bob
bob_verifying_secret = SecretKey.random()
bob_verifying_key = bob_verifying_secret.public_key()
decrypting_secret = SecretKey.random()
decrypting_key = decrypting_secret.public_key()

universal_bob = Bob.from_public_keys(verifying_key=bob_verifying_key,
                                     encrypting_key=decrypting_key,
                                     federated_only=True)
print(f'Created Universal Bob - {bytes(universal_bob.stamp).hex()}')


default_seed = "https://ibex.nucypher.network:9151"
james = "https://143.198.239.218:9151"
dream_team = [
    default_seed,
    james
]

ursulas = {Ursula.from_teacher_uri(teacher_uri=uri, federated_only=True, min_stake=0) for uri in dream_team}

# God-mode Alice
alice = Alice(federated_only=True, domain='ibex', known_nodes=ursulas)
pk = bytes(alice.stamp.as_umbral_pubkey()).hex()
print(f'Generated God-mode Alice {bytes(universal_bob.stamp).hex()}')
alice.start_learning_loop(now=True)

# Network Policy
m, n = 1, 1
label = 'dream-team'.encode()
policy = alice.grant(bob=universal_bob,
                     ursulas=ursulas,
                     label=label,
                     threshold=m,
                     shares=n,
                     duration=3600*365)
print(f'Generated network policy {bytes(policy.public_key).hex()}')

# Store artifacts
network_tmap = policy.treasure_map
network_pek = policy.public_key
universal_bob_public_key = universal_bob.public_keys(DecryptingPower)
universal_bob_secret_key = decrypting_secret
print(network_tmap, network_pek, universal_bob_public_key, universal_bob_secret_key, sep='\n')

payload = {
    'tmap': bytes(network_tmap).hex(),
    'pek': bytes(network_pek).hex(),
    'alice_public_key': bytes(alice.stamp).hex(),
    'bob_public_key': bytes(universal_bob_public_key).hex(),
    'bob_secret_key': universal_bob_secret_key.to_secret_bytes().hex()
}

filename = 'network_material.json'
with open(filename, 'w') as file:
    data = json.dumps(payload, indent=4)
    file.write(data)
    print(f'Generated network material at {filename}')
