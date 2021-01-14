Getting Started with Characters
===============================


* `A Note about Side Channels`_
* `Running an Ethereum Node`_
* `Connecting to The NuCypher Network`_
* `Alice: Grant Access to a Secret`_

    * `Setup Alice`_
    * `Grant`_

* `Enrico: Encrypt a Secret`_

    * `Setup Enrico`_
    * `Encrypt`_

* `Bob: Decrypt a Secret`_

    * `Setup Bob`_
    * `Join a Policy`_
    * `Retrieve and Decrypt`_


A Note about Side Channels
--------------------------

The NuCypher network does not store or handle an application's data; instead - it manages access *to* application data.
Management of encrypted secrets and public keys tends to be highly domain-specific - The surrounding architecture
will vary greatly depending on the throughput, sensitivity, and sharing cadence of application secrets.
In all cases, NuCypher must be integrated with a storage and transport layer in order to function properly.
Along with the transport of ciphertexts, a nucypher application also needs to include channels for Alice and Bob
to discover each other's public keys, and provide policy encrypting information to Bob and Enrico.

Side Channel Application Data
-----------------------------

* Secrets:

   * Message Kits - Encrypted Messages, or "Ciphertexts"

* Identities:

    * Alice Verifying Key - Public key used for verifying Alice
    * Bob Encrypting Key - Public key used to encrypt for Bob
    * Bob Verifying Key - Public key used to verify Bob

* Policies:

    * Policy Encrypting Key - Public key used to encrypt messages for a Policy.
    * Labels - A label for specifying a Policy's target, like a filepath


Running an Ethereum Node
------------------------

Operation of a decentralized NuCypher character [\ ``Alice``\ , ``Bob``\ , ``Ursula``\ ] requires
a connection to an Ethereum node and wallet to interact with :doc:`smart contracts </architecture/contracts>`.

For general background information about choosing a node technology and node operation,
see https://web3py.readthedocs.io/en/stable/node.html.

Connecting to The NuCypher Network
----------------------------------

Provider URI
^^^^^^^^^^^^

This example uses a local ethereum geth node's IPC-File specified by ``provider_uri``.
By default on ubuntu, the path is ``~/.ethereum/geth.ipc`` - this path
will also be logged to the geth-running console on startup.

.. important::

    While the example provided uses Ethereum mainnet, these steps can be followed for the Rinkeby Testnet with
    updated `geth` (``~/.ethereum/rinkeby/geth.ipc``) and `seed` URI (``https://ibex.nucypher.network:9151``).


Nucypher also supports alternative web3 node providers such as:

    * HTTP(S)-based JSON-RPC server e.g. ``https://<host>``
    * Websocket(Secure)-based JSON-RPC server e.g. ``ws://<host>:8080``, ``wss://<host>:8080``


Connecting Nucypher to an Ethereum Provider
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
   BlockchainInterfaceFactory.initialize_interface(provider_uri='~/.ethereum/geth.ipc')


Ursula: Untrusted Re-Encryption Proxies
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When initializing an ``Alice``\ , ``Bob``\ , or ``Ursula``\ , an initial "Stranger-\ ``Ursula``\ " is needed to perform
the role of a ``Teacher``\ , or "seednode":

.. code-block:: python

   from nucypher.characters.lawful import Ursula

   seed_uri = "<SEEDNODE URI>:9151"
   seed_uri2 = "<OTHER SEEDNODE URI>:9151"

   ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri)
   another_ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri2)


Stranger ``Ursula``\ s can be created by invoking the ``from_seed_and_stake_info`` method, then a ``list`` of ``known_nodes``
can be passed into any ``Character``\ 's init. The ``known_nodes`` will inform your character of all of the nodes
they know about network-wide, then kick-off the automated node-discovery loop:

.. code-block:: python

   from nucypher.characters.lawful import Alice
   alice = Alice(known_nodes=[ursula, another_ursula], ...)


For information on how to run a staking Ursula node via CLI,
see :doc:`Running a Worker </staking/running_a_worker>`.


Alice: Grant Access to a Secret
-------------------------------

Setup Alice
^^^^^^^^^^^

Create a NuCypher Keyring

.. code-block:: python

   from nucypher.config import NucypherKeyring
   keyring = NucypherKeyring.generate(checksum_address='0x287A817426DD1AE78ea23e9918e2273b6733a43D', password=PASSWORD)


.. code-block:: python

   from nucypher.characters.lawful import Alice, Ursula

   ursula = Ursula.from_seed_and_stake_info(seed_uri=<SEEDNODE URI>)

   # Unlock Alice's Keyring
   keyring = NucypherKeyring(account='0x287A817426DD1AE78ea23e9918e2273b6733a43D')
   keyring.unlock(password=PASSWORD)

   # Instantiate Alice
   alice = Alice(keyring=keyring, known_nodes=[ursula], provider_uri='~/.ethereum/geth.ipc')

   # Start Node Discovery
   alice.start_learning_loop(now=True)


Alice needs to know about Bob in order to grant access by acquiring Bob's public key's through
the application side channel:

.. code-block:: python

   from umbral.keys import UmbralPublicKey

   verifying_key = UmbralPublicKey.from_hex(verifying_key),
   encrypting_key = UmbralPublicKey.from_hex(encryption_key)


Grant
^^^^^

Then, Alice can grant access to Bob:

.. code-block:: python

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


Enrico: Encrypt a Secret
------------------------

Setup Enrico
^^^^^^^^^^^^

First, a ``policy_encrypting_key`` must be retrieved from the application side channel, then
to encrypt a secret using Enrico:

Encrypt
^^^^^^^

.. code-block:: python

   from nucypher.characters.lawful import Enrico

   enrico = Enrico(policy_encrypting_key=policy_encrypting_key)
   ciphertext, signature = enrico.encrypt_message(plaintext=b'Peace at dawn.')


The ciphertext can then be sent to Bob via the application side channel.

Note that Alice can get the public key even before creating the policy.
From this moment on, any Data Source (Enrico) that knows the public key
can encrypt data originally intended for Alice, but can be shared with
any Bob that Alice grants access.

``policy_pubkey = alice.get_policy_encrypting_key_from_label(label)``

Bob: Decrypt a Secret
---------------------

For Bob to retrieve a secret, the ciphertext, label, policy encrypting key, and Alice's verifying key must all
be fetched from the application side channel.  Then, Bob constructs his perspective of the policy's network actors:

Setup Bob
^^^^^^^^^

.. code-block:: python

   from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula

   # Application Side-Channel
   # --------------------------
   # label = <Side Channel>
   # ciphertext = <Side Channel>
   # policy_encrypting_key = <Side Channel>
   # alice_verifying_key = <Side Channel>

   # Everyone!
   ursula = Ursula.from_seed_and_stake_info(seed_uri=<SEEDNODE URI>)
   alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
   enrico = Enrico(policy_encrypting_key=policy_encrypting_key)

   # Generate and unlock Bob's keyring
   keyring = NucypherKeyring.generate(checksum_address='0xC080708026a3A280894365Efd51Bb64521c45147', password=PASSWORD)
   keyring.unlock(PASSWORD)

   # Make Bob
   bob = Bob(known_nodes=[ursula], checksum_address="0xC080708026a3A280894365Efd51Bb64521c45147")


Join a Policy
^^^^^^^^^^^^^

Next, Bob needs to join the policy:

.. code-block:: python

   bob.join_policy(label=label, alice_verifying_key=alice.public_keys(SigningPower), block=True)


Retrieve and Decrypt
^^^^^^^^^^^^^^^^^^^^

Then Bob can retrieve, and decrypt the ciphertext:

.. code-block:: python

   cleartexts = bob.retrieve(label=label,
                             message_kit=ciphertext,
                             data_source=enrico,
                             alice_verifying_key=alice.public_keys(SigningPower))
