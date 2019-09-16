# NuCypher Quickstart


## A Note about Side-Channels

The NuCypher network does not store your applications data; Instead - it manages access *to* your
applications data. Management of encrypted secrets and public keys is highly application-specific - 
In general, nucypher needs to be integrated with a storage or transport layer to function properly.
Along with the transport of ciphertext, the application also needs to include 
facilities for several other pieces of cryptographic material, specifically, channels
for Alice and Bob to discover each-others public keys, as well as a way to provide policy public keys 
to Bob and Enrico.
 
Side Channel Data:

- Message Kits (Ciphertext)
- Labels
- Alice Verifying Key
- Bob Encrypting Key
- Bob Verifying Key
- Policy Encrypting Key 

## Alice: Grant Access to a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Ursula
from datetime import datetime, timedelta

# Application Side-Channel

# bob_encrypting_key = <Side Channel>
# bob_verifying_key = <Side Channel>

ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151')
alice = Alice(checksum_address='', known_nodes=[ursula])
bob = Bob.from_public_keys(verifying_key=bob_verifying_key, encrypting_key=bob_encrypting_key)

expiration = datetime.now() + timedelta(days=5)  # Five days from now.
policy = alice.grant(bob,
                     label=b'my-secret-stuff',
                     m=2, n=3,
                     expiration=expiration)

policy_encrypting_key = policy.public_key
```

Note that Alice can get the public key even before creating the policy.
From this moment on, any Data Source (Enrico) that knows the public key
can encrypt data originally intended for Alice, but that can be shared with
any Bob that Alice grants access.

`policy_pubkey = alice.get_policy_encrypting_key_from_label(label)`


## Enrico: Encrypt a Secret

```python
from nucypher.characters.lawful import Enrico

# Application Side-Channel

# policy_encrypting_key = <Side Channel>

enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
ciphertext = enrico.encrypt_message(message=b'Peace at dawn.')
```


## Bob: Decrypt a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula


# Application Side-Channel

# label = <Side Channel>
# ciphertext = <Side Channel>
# policy_encrypting_key = <Side Channel>
# alice_verifying_key = <Side Channel>

# Everyone!
ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151')
alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
bob = Bob(known_nodes=[ursula])
enrico = Enrico(policy_encrypting_key=policy_encrypting_key)

cleartext = bob.retrieve(label=label,
                         message_kit=ciphertext,
                         data_source=enrico,
                         alice_verifying_key=alice.verifying_key)
```
