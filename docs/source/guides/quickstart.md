# NuCypher Quickstart


## A Note about Side Channels

The NuCypher network does not store or handle an application's data; instead - it manages access *to* application data.
Management of encrypted secrets and public keys tends to be highly domain-specific - The surrounding architecture
will vary greatly depending on the throughput, sensitivity, and sharing cadence of application secrets.
In all cases, NuCypher must be integrated with a storage and transport layer in order to function properly.
Along with the transport of ciphertexts, a nucypher application also needs to include channels for Alice and Bob 
to discover each other's public keys, and provide policy encrypting information to Bob and Enrico.
 
##### Side Channel Data:
  - Secrets:
    - Message Kits (Ciphertext)
  - Identities:
    - Alice Verifying Key
    - Bob Encrypting Key
    - Bob Verifying Key
  - Policies:
    - Policy Encrypting Key 
    - Labels

## Running an Ethereum Node

Operation of a decentralized NuCypher character [`Alice`, `Bob`, `Ursula`] requires
a connection to an Ethereum node and wallet.

To run a Goerli-connected Geth node in *fast* syncing mode:

```bash
$ geth --goerl
```

To run a Goerli-connected Geth node in *light* syncing mode:

```bash
$ geth --goerl --syncmode light
```

Note that using `--syncmode light` is not 100% stable but can be a life savior when using 
a mobile connection (or congested hackathon wifi...).

### Provider URI

Nucypher uses the node's IPC-File to communicate, specified by `provider_uri`.
By default in ubuntu, the path is `~/.ethereum/goerli/geth.ipc` - This path
will also be logged to the geth-running console on startup. 

Connect to the Geth Console to test your ethereum node's IPC:
```bash
$ geth attach ~/.ethereum/goerli/geth.ipc
```

### Wallets

To list available accounts on your geth node:

```bash
$ geth attach ~/.ethereum/goerli/geth.ipc
> eth.accounts
["0x287a817426dd1ae78ea23e9918e2273b6733a43d", "0xc080708026a3a280894365efd51bb64521c45147"]
```

Hardware wallet addresses will also be listed here if one is attached to the system hardware.
Note that the Geth console does not return EIP-55 compliant checksum addresses, and instead will output
the *lowercase* version of the address.  Since Nucypher requires EIP-55 checksum addresses, you will need 
to convert your address to checksum format:

```bash
> web3.toChecksumAddress(eth.accounts[0])
"0x287A817426DD1AE78ea23e9918e2273b6733a43D"
```

## Connecting to The NuCypher Network

### Connecting Nucypher to an Ethereum Provider

```python
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
BlockchainInterfaceFactory.initialize_interface(provider_uri='~/.ethereum/goerli/geth.ipc')
```

### Ursula: Untrusted Re-Encryption Proxies

When initializing an `Alice`, `Bob`, or `Ursula`, an initial "Stranger-`Ursula`" is needed to perform 
the role of a `Teacher`, or "seednode":

```python
from nucypher.characters.lawful import Ursula, Alice

ursula = Ursula.from_seed_and_stake_info(seed_uri=<URI>, federated_only=False)  # ie. https://0.0.0.0:9151
another_ursula = Ursula.from_seed_and_stake_info(seed_uri=<URI>, federated_only=False)
```

Stranger `Ursula`s can be created by invoking the `from_seed_and_stake_info` method, then a `list` of `known_nodes`
can be passed into any `Character`'s init. The `known_nodes` will inform your character of all of the nodes
they know about network-wide, then kick-off the automated node-discovery loop:

```python
alice = Alice(known_nodes=[ursula, another_ursula], ...)
```

## Alice: Grant Access to a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Ursula
from nucypher.network.middleware import RestMiddleware
from nucypher.blockchain.eth.registry import InMemoryContractRegistry

# Application Side-Channel
# --------------------------
# bob_encrypting_key = <Side Channel>
# bob_verifying_key = <Side Channel>

ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151', federated_only=False)
alice = Alice(known_nodes=[ursula],
              checksum_address="0x287A817426DD1AE78ea23e9918e2273b6733a43D", 
              registry=InMemoryContractRegistry.from_latest_publication(),
              network_middleware=RestMiddleware())
bob = Bob.from_public_keys(verifying_key=bob_verifying_key, encrypting_key=bob_encrypting_key)
```

```python
from datetime import datetime
import maya

#
# Grant
#

policy_end_datetime = maya.now() + datetime.timedelta(days=5)  # Five days from now
policy = alice.grant(bob,
                     label=b'my-secret-stuff',
                     m=2, n=3,
                     expiration=policy_end_datetime)

policy_encrypting_key = policy.public_key
```

## Enrico: Encrypt a Secret

```python
from nucypher.characters.lawful import Enrico

# Application Side-Channel
# --------------------------
# policy_encrypting_key = <Side Channel>

enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
ciphertext, signature = enrico.encrypt_message(message=b'Peace at dawn.')
```
    
Note that Alice can get the public key even before creating the policy.
From this moment on, any Data Source (Enrico) that knows the public key
can encrypt data originally intended for Alice, but can be shared with
any Bob that Alice grants access.

`policy_pubkey = alice.get_policy_encrypting_key_from_label(label)`


## Bob: Decrypt a Secret

```python
from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.network.middleware import RestMiddleware

# Application Side-Channel
# --------------------------
# label = <Side Channel>
# ciphertext = <Side Channel>
# policy_encrypting_key = <Side Channel>
# alice_verifying_key = <Side Channel>

# Everyone!
ursula = Ursula.from_seed_and_stake_info(seed_uri='https://0.0.0.0:9151', federated_only=False)
alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
bob = Bob(known_nodes=[ursula],
          checksum_address="0xc080708026a3a280894365efd51bb64521c45147",
          registry=InMemoryContractRegistry.from_latest_publication(),
          network_middleware=RestMiddleware())
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
