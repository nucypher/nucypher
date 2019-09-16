# NuCypher Quickstart


## A Note about Side-Channels

The NuCypher network does not store your application's data; Instead - it manages access *to* your
application's data. Management of encrypted secrets and public keys is highly application-specific - 
In general, nucypher needs to be integrated with a storage or transport layer to function properly.
Along with the transport of ciphertext, the application also needs to include 
facilities for several other pieces of cryptographic material, specifically, channels
for Alice and Bob to discover each-others public keys, as well as a way to provide policy public keys 
to Bob and Enrico.
 
##### Side Channel Data:
  - Secrets:
    - Message Kits (Ciphertext)
    - Labels
  - Identities:
    - Alice Verifying Key
    - Bob Encrypting Key
    - Bob Verifying Key
  - Policies:
    - Policy Encrypting Key 


## Connecting to the NuCypher Network

### Running an Ethereum Node

Operation of nucypher cryptological characters `Alice`, `Bob`, and `Ursula` require
a running ethereum node and wallet (We recommend Geth).

To run a Goerli connected Geth node:
```bash
$ geth --goerl
```

### Provider URI

Nucypher uses the node's IPC-File to communicate, specified by `provider_uri`.
By default in ubuntu, the path is `~/.ethereum/goerli/geth.ipc` - This path
will also be logged to the geth-running console on startup. 

### Ursula: Untrusted Re-Encryption Proxies

When initializing an `Alice`, `Bob`, or `Ursula`, an initial "Stranger-`Ursula`" is needed to perform 
the role of a `Teacher`, or "seednode".  The `known_nodes` will inform your character of all of the nodes
they know about network-wide, then kick-off the automated node-discovery loop.

Stranger `Ursula`s can be created by invoking the `from_seed_and_stake_info` method, then a `list` of `known_nodes`
can be passed into any `Character`'s init:
```python
from nucypher.characters.lawful import Ursula, Alice

ursula = Ursula.from_seed_and_stake_info(seed_uri=<URI>)  # ie. https://0.0.0.0:9151
another_ursula = Ursula.from_seed_and_stake_info(seed_uri=<URI>)

alice = Alice(checksum_address='0xdeadbeef',
              provider_uri=<PROVIDER URI>,
              known_nodes=[ursula, another_ursula])
```

## Alice: Grant Access to a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Ursula

# Application Side-Channel
# --------------------------
# bob_encrypting_key = <Side Channel>
# bob_verifying_key = <Side Channel>

ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151')
alice = Alice(checksum_address='0xdeadbeef', 
              provider_uri=<PROVIDER URI>,
              known_nodes=[ursula])
bob = Bob.from_public_keys(verifying_key=bob_verifying_key, encrypting_key=bob_encrypting_key)
```

```python
from datetime import datetime, timedelta

#
# Grant
#

expiration = datetime.now() + timedelta(days=5)  # Five days from now.
policy = alice.grant(bob,
                     label=b'my-secret-stuff',
                     m=2, n=3,
                     expiration=expiration)

policy_encrypting_key = policy.public_key
```

Note that Alice can get the public key even before creating the policy.
From this moment on, any Data Source (Enrico) that knows the public key
can encrypt data originally intended for Alice, but can be shared with
any Bob that Alice grants access.

`policy_pubkey = alice.get_policy_encrypting_key_from_label(label)`


## Enrico: Encrypt a Secret

```python
from nucypher.characters.lawful import Enrico

# Application Side-Channel
# --------------------------
# policy_encrypting_key = <Side Channel>

enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
ciphertext = enrico.encrypt_message(message=b'Peace at dawn.')
```


## Bob: Decrypt a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula


# Application Side-Channel
# --------------------------
# label = <Side Channel>
# ciphertext = <Side Channel>
# policy_encrypting_key = <Side Channel>
# alice_verifying_key = <Side Channel>

# Everyone!
ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151')
alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
bob = Bob(checksum_address='0xdeadbeef',
          provider_uri=<PROVIDER URI>,
          known_nodes=[ursula])
enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
```

```python
#
# Decrypt
#

cleartext = bob.retrieve(label=label,
                         message_kit=ciphertext,
                         data_source=enrico,
                         alice_verifying_key=bytes(alice.stamp))
```
