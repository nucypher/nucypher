Getting Started with Characters
===============================

* `A Note about Side Channels`_
* `Alice: Grant Access to a Secret`_
* `Enrico: Encrypt a Secret`_
* `Bob: Decrypt a Secret`_


A Note about Side Channels
--------------------------

The NuCypher network does not store or handle an application's data; instead - it manages access *to* application data.
Management of encrypted secrets and public keys tends to be highly domain-specific - the surrounding architecture
will vary greatly depending on the throughput, sensitivity, and sharing cadence of application secrets.

In all cases, NuCypher must be integrated with a storage and transport layer in order to function properly.
Along with the transport of ciphertexts, a nucypher application also needs to include channels for Alice and Bob
to discover each other's public keys, and provide policy encrypting information to Bob and Enrico.


The Application Side Channel
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


Choosing an Ethereum Provider
-----------------------------

Operation of a decentralized NuCypher character [\ ``Alice``\ , ``Bob``\ , ``Ursula``\ ] requires
a connection to an Ethereum node and wallet to interact with :doc:`smart contracts </architecture/contracts>`.

For general background information about choosing a node technology and node operation,
see https://web3py.readthedocs.io/en/stable/node.html.


Ursula: Untrusted Re-Encryption Proxies
----------------------------------------

When initializing an ``Alice``\ , ``Bob``\ , or ``Ursula``\ , an initial "Stranger-\ ``Ursula``\ " is needed to perform
the role of a ``Teacher``\ , or "seednode":

.. code-block:: python

   from nucypher.characters.lawful import Ursula

   seed_uri = "<SEEDNODE URI>:9151"
   seed_uri2 = "<OTHER SEEDNODE URI>:9151"

   ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri)
   another_ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri2)


.. note::

    While any nucypher worker node can be used to seed your peers, NuCypher maintains
    workers that can be used as seed nodes:

    - mainnet: ``https://mainnet.nucypher.network:9151``
    - lynx: ``https://lynx.nucypher.network:9151``
    - ibex: ``https://ibex.nucypher.network:9151``

    .. code::

        seed_uri = 'https://lynx.nucypher.network:9151'
        ursula = Ursula.from_seed_and_stake_info(seed_uri=seed_uri)


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

Setup Alice Keys
^^^^^^^^^^^^^^^^

Alice uses an ethereum wallet to create publish access control policies to the ethereum blockchain,
and a set of related keys derived from a *"nucypher keystore"*.

First, instantiate a ``Signer`` to use for signing transactions. This is an API for Alice's ethereum
wallet, which can be an keystore file, trezor, ethereum node, or clef.  The signer type and address
are specified using a ``signer_uri``:

- Trezor Hardware Wallet: ``'trezor'``
- Keystore directory or keyfile: ``'keystore://<ABSOLUTE PATH TO KEYSTORE>'``
- Local geth node: ``'web3://<ABSOLUTE PATH TO IPC ENDPOINT>'``
- Clef external signer: ``'clef'``

Here are some examples of usage:

.. code-block:: python

    from nucypher.blockchain.eth.signers import Signer
    wallet = Signer.from_signer_uri('<YOUR SIGNER URI>')

    # Trezor Wallet
    trezor = Signer.from_signer_uri('trezor')

    # Local Geth Wallet
    geth_signer = Signer.from_signer_uri('web3:///home/user/.ethereum/geth.ipc')

    # Keyfile Wallet
    software_wallet = Signer.from_signer_uri('keystore:///home/user/.ethereum/keystore/<KEY FILENAME>')

If you are using a software wallet, be sure to unlock it:

.. code-block:: python

    # Unlocking a software wallet
    >>> software_wallet.unlock_account(account='0x287A817426DD1AE78ea23e9918e2273b6733a43D', password=<ETH_PASSWORD>)


Next, create a NuCypher Keystore. This step will generate a new set of related private keys used for nucypher cryptography operations,
which can be integrated into your application's user on-boarding or setup logic. These keys will be stored on the disk,
encrypted-at-rest using the supplied password. Use the same account as the signer; Keystores are timestamped and named by public key,
so be sure to specify an account you control with a ``Signer``.

.. code-block:: python

   from nucypher.crypto.keystore import Keystore

   keystore = Keystore.generate(password=NEW_PASSWORD)  # used to encrypt nucypher private keys

   # Public Key
   >>> keystore.id
   e76f101f35846f18d80bfda5c61e9ec2

   # The root directory containing the private keys
   >>> keystore.keystore_dir
   '/home/user/.local/share/nucypher/keystore'


After generating a keystore, any future usage can decrypt the keys from the disk:

.. code-block:: python

   from nucypher.crypto.keystore import Keystore

   # Restore an existing Alice keystore
   path = '/home/user/.local/share/nucypher/keystore/1621399628-e76f101f35846f18d80bfda5c61e9ec2.priv'
   keystore = Keystore(path)

   # Unlock Alice's keystore
   keystore.unlock(password=NUCYPHER_PASSWORD)


.. code-block:: python

   from nucypher.characters.lawful import Alice, Ursula

   # Instantiate a default peer (optional)
   ursula = Ursula.from_seed_and_stake_info(seed_uri='https://lynx.nucypher.network:9151')

   # Instantiate Alice
   alice = Alice(
       keystore=keystore,            # NuCypher Keystore
       known_nodes=[ursula],         # Peers (Optional)
       signer=signer,                # Alice Wallet
       provider_uri=<RPC ENDPOINT>,  # Ethereum RPC endpoint
       domain='lynx'                 # NuCypher network (mainnet, lynx, ibex)
   )

   # Alice is identified by her ethereum address
   alice.checksum_address
   '0x287A817426DD1AE78ea23e9918e2273b6733a43D'

   # Start node discovery
   alice.start_learning_loop(now=True)


Alice needs to know Bob's public keys in order to grant him access. Alice's are expected to acquiring Bob's public
keys through the application side channel.  Umbral public keys used in NuCypher's proxy re-encryption can be restored
from hex for API usage:

.. code-block:: python

   from umbral.keys import UmbralPublicKey

   verifying_key = UmbralPublicKey.from_hex(verifying_key_as_hex),
   encrypting_key = UmbralPublicKey.from_hex(encryption_key_as_hex)


Grant
^^^^^

Alice can grant access to Bob using his public keys:

.. code-block:: python

   from umbral.keys import UmbralPublicKey
   from nucypher.characters.lawful import Bob
   from datetime import timedelta
   from web3 import Web3
   import maya


   # Deserialize bob's public keys from the application side-channel
   verifying_key = UmbralPublicKey.from_hex(verifying_key_as_hex),
   encrypting_key = UmbralPublicKey.from_hex(encryption_key_as_hex)

   # Make a representation of Bob
   bob = Bob.from_public_keys(verifying_key=bob_verifying_key,  encrypting_key=bob_encrypting_key)

   policy = alice.grant(
       bob,
       label=b'my-secret-stuff',   # Send to Bob via side channel
       m=2,                        # Threshold shares for access
       n=3,                        # Total nodes with shares
       rate=Web3.toWei(50, 'gwei'),  # 50 Gwei is the minimum rate (per node per period)
       expiration= maya.now() + timedelta(days=5)  # Five days from now
    )

   # The policy's public key
   policy_encrypting_key = policy.public_key


Putting it all together, here's an example starter script for granting access using a
software wallet and an existing keystore:

.. code-block:: python

    from nucypher.blockchain.eth.signers import Signer
    from nucypher.crypto.keystore import Keystore
    from nucypher.characters.lawful import Alice, Bob
    from umbral.keys import UmbralPublicKey
    from datetime import timedelta
    from web3 import Web3
    import maya


    # Restore Existing NuCypher Keystore
    keystore = Keystore(keystore_path=path)
    keystore.unlock('YOUR KEYSTORE PASSWORD')

    # Ethereum Software Wallet
    wallet = Signer.from_signer_uri("keystore:///home/user/.ethereum/goerli/keystore/UTC--2021...0278ad02...')
    wallet.unlock_account('0x287A817426DD1AE78ea23e9918e2273b6733a43D', 'SOFTWARE WALLET PASSWORD')

    # Make Alice
    alice = Alice(
        domain='lynx',  # testnet
        provider_uri='GOERLI RPC ENDPOINT',
        keystore=keystore,
        signer=wallet,
    )

    # From Public Key Side Channel
    verifying_key = UmbralPublicKey.from_hex('0278ad02da8083aea357a8ed675dcc0b6e9c78557c506ea10b102b4b282c006b12')
    encrypting_key = UmbralPublicKey.from_hex('03ec6b4e1f2b7d06ac544dde86730f9a4047e80a0a4d3c1566e88afe4bb449bdd9')

    # Make Stranger-Bob
    bob = Bob.from_public_keys(verifying_key=verifying_key, encrypting_key=encrypting_key)

    # Grant Bob Access
    policy = alice.grant(
        bob,
        label=b'my-secret-stuff',     # Send to Bob via side channel
        m=2,                          # Threshold shares for access
        n=3,                          # Total nodes with shares
        rate=Web3.toWei(50, 'gwei'),  # 50 Gwei is the minimum rate (per node per period)
        expiration= maya.now() + timedelta(days=5)  # Five days from now
     )


Enrico: Encrypt a Secret
------------------------

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

Bob's setup is similar to Alice's above.

.. code-block:: python

   from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula

   # Application Side-Channel
   # --------------------------
   # label = <Side Channel>
   # ciphertext = <Side Channel>
   # policy_encrypting_key = <Side Channel>
   # alice_verifying_key = <Side Channel>

   # Everyone!
   ursula = Ursula.from_seed_and_stake_info(seed_uri='https://lynx.nucypher.network:9151')
   alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
   enrico = Enrico(policy_encrypting_key=policy_encrypting_key)

   # Restore Existing Bob keystore
   keystore = Keystore(keystore_path=path)

   # Unlock keystore and make Bob
   keystore.unlock(PASSWORD)
   bob = Bob(
       keystore=keystore,
       known_nodes=[ursula],
       domain='lynx'
   )


Join a Policy
^^^^^^^^^^^^^

Next, Bob needs to join the policy using the policy label and alice's public key.  Bob needs
to retrieve both of these from the application side channel first.

.. code-block:: python

   # Make alice from known public key (from application side channel)
   alice = Alice.from_public_keys(verifying_key=alice_verifying_key)

   # Use alice's public key and the label to join the access policy
   alice_public_key = alice.public_keys(SigningPower)
   bob.join_policy(
       label=label,
       # We are using Alice both as a policy creator and as a publisher
       publisher_verifying_key=alice_public_key,
   )


Retrieve and Decrypt
^^^^^^^^^^^^^^^^^^^^

Then Bob can retrieve and decrypt the ciphertext:

.. code-block:: python

   cleartexts = bob.retrieve(
       label=label,
       message_kit=ciphertext,
       data_source=enrico,
       alice_verifying_key=alice_public_key
   )
