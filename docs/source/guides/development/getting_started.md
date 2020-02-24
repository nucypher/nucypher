# Getting Started with Characters

- [Side Channels](#a-note-about-side-channels)
- [Running an Ethereum Node](#running-an-ethereum-node)
- [Connecting Nucypher to an Etheruem Node](#connecting-to-the-nucypher-network)

- [Alice: Grant Access to a Secret](#alice-grant-access-to-a-secret)
    + [Setup](#setup-alice)
    + [Grant](#grant)

- [Enrico: Encrypt a Secret](#enrico-encrypt-a-secret)
    * [Setup](#setup-enrico)
    * [Encrypt](#encrypt)

- [Bob: Decrypt a Secret](#bob-decrypt-a-secret)
    * [Setup](#setup-bob)
    * [Join a Policy](#join-a-policy)
    * [Decrypt](#retrieve-and-decrypt)



## A Note about Side Channels

The NuCypher network does not store or handle an application's data; instead - it manages access *to* application data.
Management of encrypted secrets and public keys tends to be highly domain-specific - The surrounding architecture
will vary greatly depending on the throughput, sensitivity, and sharing cadence of application secrets.
In all cases, NuCypher must be integrated with a storage and transport layer in order to function properly.
Along with the transport of ciphertexts, a nucypher application also needs to include channels for Alice and Bob 
to discover each other's public keys, and provide policy encrypting information to Bob and Enrico.
 
##### Side Channel Application Data
  - Secrets:
    - Message Kits - Encrypted Messages, or "Ciphertexts"
  - Identities:
    - Alice Verifying Key - Public key used for verifying Alice 
    - Bob Encrypting Key - Public key used to encrypt for Bob
    - Bob Verifying Key - Public key used to verify Bob
  - Policies:
    - Policy Encrypting Key - Public key used to encrypt messages for a Policy.
    - Labels - A label for specifying a Policy's target, like a filepath

## Running an Ethereum Node

Operation of a decentralized NuCypher character [`Alice`, `Bob`, `Ursula`] requires
a connection to an Ethereum node and wallet to interact with smart
contracts (<https://docs.nucypher.com/en/latest/architecture/contracts.html>). 

For general background information about choosing a node technology and operation,
see <https://web3py.readthedocs.io/en/stable/node.html>. 

In this guide, a local Geth node connected to the Goerli Testnet is used.
For detailed information on using the geth CLI and Javascript console,
see <https://geth.ethereum.org/interface/Command-Line-Options>.

To run a Goerli-connected Geth node in *fast* syncing mode:

```bash
$ geth --goerli
```

To run a Goerli-connected Geth node in *light* syncing mode:

```bash
$ geth --goerli --syncmode light
```

Note that using `--syncmode light` is not 100% stable but can be a life savior when using 
a mobile connection (or congested hackathon wifi...).

Connect to the Geth Console to test your ethereum node's IPC:
```bash
$ geth attach ~/.ethereum/goerli/geth.ipc
```

### Wallets

To list available accounts on your geth node (Hardware wallet addresses will also be listed here 
if one is attached to the system hardware):

```bash
$ geth attach ~/.ethereum/goerli/geth.ipc
> eth.accounts
["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]
```

To create a new software based Geth account:

```bash
$ geth attach ~/.ethereum/goerli/geth.ipc
> personal.newAccount()
...
"0xc080708026a3a280894365efd51bb64521c45147"
```

Note that the Geth console does not return EIP-55 compliant checksum addresses, and instead will output
the *lowercase* version of the address.  Since Nucypher requires EIP-55 checksum addresses, you will need 
to convert your address to checksum format:

```javascript
> web3.toChecksumAddress(eth.accounts[0])
"0x287A817426DD1AE78ea23e9918e2273b6733a43D"
```

## Connecting to The NuCypher Network

### Provider URI

Nucypher uses the ethereum node's IPC-File to communicate, specified by `provider_uri`.
By default in ubuntu, the path is `~/.ethereum/goerli/geth.ipc` - This path
will also be logged to the geth-running console on startup. 

### Connecting Nucypher to an Ethereum Provider

```python
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
BlockchainInterfaceFactory.initialize_interface(provider_uri='~/.ethereum/goerli/geth.ipc')
```

### Ursula: Untrusted Re-Encryption Proxies

When initializing an `Alice`, `Bob`, or `Ursula`, an initial "Stranger-`Ursula`" is needed to perform 
the role of a `Teacher`, or "seednode":

```python
from nucypher.characters.lawful import Ursula

seed_uri = "discover.nucypher.network:9151"
seed_uri2 = "104.248.215.144:9151"

ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri)
another_ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri2)
```

Stranger `Ursula`s can be created by invoking the `from_seed_and_stake_info` method, then a `list` of `known_nodes`
can be passed into any `Character`'s init. The `known_nodes` will inform your character of all of the nodes
they know about network-wide, then kick-off the automated node-discovery loop:

```python
from nucypher.characters.lawful import Alice
alice = Alice(known_nodes=[ursula, another_ursula], ...)
```

For information on how to run a staking Ursula node via CLI,
see [Running a Network Node](/guides/network_node/network_node).

## Alice: Grant Access to a Secret

### Setup Alice

#### Create a NuCypher Keyring

```python
from nucypher.config import NucypherKeyring
keyring = NucypherKeyring.generate(checksum_address='0x287A817426DD1AE78ea23e9918e2273b6733a43D', password=PASSWORD)
```

```python
from nucypher.characters.lawful import Alice, Ursula

ursula = Ursula.from_seed_and_stake_info(seed_uri='discover.nucypher.network:9151')

# Unlock Alice's Keyring
keyring = NucypherKeyring(account='0x287A817426DD1AE78ea23e9918e2273b6733a43D')
keyring.unlock(password=PASSWORD)

# Instantiate Alice
alice = Alice(keyring=keyring, known_nodes=[ursula], provider_uri='~/.ethereum/goerli/geth.ipc')

# Start Node Discovery
alice.start_learning_loop(now=True)
```

Alice needs to know about Bob in order to grant access by acquiring Bob's public key's through 
the application side channel:

```python
from umbral.keys import UmbralPublicKey

verifying_key = UmbralPublicKey.from_hex(verifying_key),
encrypting_key = UmbralPublicKey.from_hex(encryption_key)
```

### Grant

Then, Alice can grant access to Bob:

```python
from nucypher.characters.lawful import Bob
from datetime import timedelta
import maya


bob = Bob.from_public_keys(verifying_key=bob_verifying_key,  encrypting_key=bob_encrypting_key)
policy_end_datetime = maya.now() + timedelta(days=5)  # Five days from now
policy = alice.grant(bob,
                     label=b'my-secret-stuff',  # Sent to Bob via side channel
                     m=2, n=3,
                     expiration=policy_end_datetime)

policy_encrypting_key = policy.public_key
```

## Enrico: Encrypt a Secret

### Setup Enrico

First, A `policy_encrypting_key` must be retrieved from the application side channel, then 
to encrypt a secret using Enrico:

### Encrypt

```python
from nucypher.characters.lawful import Enrico

enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
ciphertext, signature = enrico.encrypt_message(message=b'Peace at dawn.')
```

The ciphertext can then be sent to Bob via the application side channel.

Note that Alice can get the public key even before creating the policy.
From this moment on, any Data Source (Enrico) that knows the public key
can encrypt data originally intended for Alice, but can be shared with
any Bob that Alice grants access.

`policy_pubkey = alice.get_policy_encrypting_key_from_label(label)`


## Bob: Decrypt a Secret

For Bob to retrieve a secret, The ciphertext, label, policy encrypting key, and Alice's veryfying key must all
be fetched from the application side channel.  Then, Bob constructs his perspective of the policy's network actors:

### Setup Bob

```python
from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula

# Application Side-Channel
# --------------------------
# label = <Side Channel>
# ciphertext = <Side Channel>
# policy_encrypting_key = <Side Channel>
# alice_verifying_key = <Side Channel>

# Everyone!
ursula = Ursula.from_seed_and_stake_info(seed_uri='discover.nucypher.network:9151')
alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
enrico = Enrico(policy_encrypting_key=policy_encrypting_key)

# Generate and unlock Bob's keyring
keyring = NucypherKeyring.generate(checksum_address='0xC080708026a3A280894365Efd51Bb64521c45147', password=PASSWORD)
keyring.unlock(PASSWORD)

# Make Bob
bob = Bob(known_nodes=[ursula], checksum_address="0xC080708026a3A280894365Efd51Bb64521c45147")
```

### Join a Policy

Next, Bob needs to join the policy:

```python
bob.join_policy(label=label, alice_verifying_key=alice.public_keys(SigningPower), block=True)
```

### Retrieve and Decrypt
Then Bob can retrieve, and decrypt the ciphertext:

```python
cleartexts = bob.retrieve(label=label,
                          message_kit=ciphertext,
                          data_source=enrico,
                          alice_verifying_key=alice.public_keys(SigningPower))
```
