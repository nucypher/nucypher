==========================
Frequently Asked Questions
==========================

The answers in the FAQ regularly reference the network characters "**Alice**," "**Bob**," "**Ursula**," and "**Enrico**." For a more in-depth introduction to each character, head over to :ref:`character-concepts`.

**Alice** is the *data owner*. She wants to share some data with **Bob**, *the data recipient*.

**Enrico** *encrypts data on behalf of Alice* to produce the ciphertext (more specifically a MessageKit). In many cases (though not all!), **Enrico** is controlled by **Alice**.

**Ursula** serves as the "*proxy*" in this proxy re-encryption scheme and *re-encrypts the ciphertext encrypted under Alice's key to a ciphertext that will be decryptable under Bob's key*.


General
-------

Q: How do I know if the PRE Application is a good fit for my use case?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A centralized approach to access control means users are forced to trust the system(s) with the plaintext version of
their private data, and usually are given little insight into who exactly they are trusting. The PRE Application’s decentralized
access control system offers developers, and their users, a departure from this opaque and trust-dependent paradigm.
When integrated, ``nucypher`` enables end-to-end encrypted data sharing workflows within applications – but
crucially, without sacrificing scalability, redundancy or performance – and applicable to data payloads of
any form, size, structure, sensitivity or production cadence. Users enjoy the same sharing powers they
currently take for granted but are **not** obliged to trust the developers of the application or
third-party access control services (e.g. centralized servers or key management systems) with their data.

Q: How is PRE different from more traditional public key infrastructure (PKI)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For an in-depth analysis of this topic, see our blog post entitled "`Three things that NuCypher's "Ursula" can do that vanilla public-key cryptography can't <https://blog.nucypher.com/why-use-nucyphers-ursula-instead-of-traditional-public-key-cryptography/>`_".

Q: If a dApp utilizes the PRE Application, is there an ETH gas fee associated with each re-encryption of encrypted data?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

There is a gas fee associated with granting and revoking policies, but re-encryption does not involve an on-chain transaction so there is no gas fee.
Previously, policy management occurred on Ethereum mainnet.  As of nucypher 6.0, policy management occurs on the Polygon sidechain
by default and results in lower gas fees.

Q: How much trust do we place in Ursula, the proxy?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ursulas are “semi-trusted” in the sense that Alice must trust Ursula to revoke a policy once it expires or if instructed to do so (by Alice). Alice and Bob also trust Ursula to be responsive and perform the re-encryption correctly so that Bob can access the data.
Importantly, Ursulas are not trusted with access to any underlying plaintext or private keys.

Q: How do we verify that Ursula has performed the re-encryption correctly?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every time Ursula produces a re-encryption result, she computes a zero-knowledge proof that proves that the re-encryption she just performed is correct,
without disclosing any kind of secret information. This  correctness proof is publicly verifiable, so if
someone detects incorrect re-encryptions coming from an Ursula, these faulty proofs can be sent to a smart contract that will slash the stake
associated with that Ursula. However, in a normal scenario, with Ursula working correctly, there’s no need for correctness proofs to be
submitted on-chain.

Q: How much trust do we place in Enrico?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enrico is often (not always!) controlled by Alice. Enrico must be trusted to perform the encryption correctly and to not disclose the secret key.
However, these things are out of our (cryptographic) control. Additionally, Alice can decrypt (and thus read) anything encrypted by Enrico.

Q: Where are Bobs’ requests handled?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bobs' requests are handled off-chain.

Q: Why are Bobs' requests handled off-chain?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It allows for a very small/lightweight Bob.

Q: Why can't my users reuse their Ethereum wallet keys when creating a sharing policy?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Avoiding key reuse is a strong defense-in-depth measure against cryptographic and software flaws. While it is
possible to use your ETH keys in ``nucypher``, we strongly advise against such a practice. It is best to keep these
sets of keys separate.

Q: How can I get help integrating nucypher into my application?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :doc:`/application_development/getting_started`. To chat directly with our team, please join our `Discord <https://discord.gg/Threshold>`_.

Q: How do I integrate nucypher if my application is not written in Python?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Nucypher also provides web integration. See :ref:`web-development`.


Running a Node
--------------

*These are questions related to running a PRE node on the Threshold Network.*

Q: What kind of token is T?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

T is an implementation of the ERC20 standard deployed onto the Ethereum blockchain.

Q: How many Ursulas per period collect Inflation rewards (T)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every Ursula that is “online” and “available” will receive a cut based on the
size of their stake proportional to the overall T staked in the network.


Q: What are the recommended server specifications for running a PRE Application node?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`node-requirements`.


Q: How do I set up a network node?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`running-a-node`.

Q: Is there a guide for Windows?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Our guide is intended for Linux - we do not officially support Windows.

Q: How computationally expensive is the re-encryption operation?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A re-encryption operation is very lightweight (in the order of milliseconds) and is comparable to computing an ECDSA signature.

Q: Where is my Ursula config path?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Default configuration and logging paths can be displayed using the command line:

Configuration path - ``nucypher --config-path``
Default logging path - ``nucypher --logging-path``

On Ubuntu/Debian the default Ursula configuration path is``$HOME/.local/share/nucypher/ursula.json``.
However, if you have more than one Ursula configuration, the filename will include the checksum address:``$HOME/.local/share/nucypher/ursula-0xdeadbeef.json``.

To inspect the config path for configuration files run ``ls $(nucypher --config-path)``.

Q: What is the difference between Standard Installation and Development Installation?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Development Installation is only needed for developing with ``nucypher``. You don't need to use
it unless you plan to make changes to the codebase. If you are simply staking/running a node, you
only need the Standard Installation

Q: How do I know that my node is set up correctly?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is **ONLY** a heuristic to ensure that your node is running correctly, it doesn't guarantee your node is setup correctly:

#. Ensure that your Ursula node is up and running (logs/terminal):

   .. code::

        Starting Ursula on xxx.xxx.xxx.xxx:9151
        Connecting to <NETWORK>
        Working ~ Keep Ursula Online!

#. Ensure that your node uses the correct IP address and can be accessed via port 9151 from an outside
   connection eg. cell phone, another computer etc. by navigating to ``https://<node_ip>:9151/status``

Q: What's the best way to run an Ursula node in the background?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using docker :ref:`Docker <run-ursula-with-docker>`

Q: When installing on Docker, what do I input for <NETWORK NAME>?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``mainnet`` if you want to interact with the PRE Application network, otherwise use the relevant testnet.

Q: How can I check for currently available staking rewards?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On the `Threshold Dashboard UI <https://dashboard.threshold.network>`_.

Q: What is a fleet state?
~~~~~~~~~~~~~~~~~~~~~~~~~

A symbol that represents your node's view of the network. It is just a
graphic checksum, so a minor change in the fleet (e.g., a new node joins, a node disappears, etc.)
will produce a completely different fleet state symbol. A node can have a
different fleet state than others, which may indicate that a different number of peers are accessible from
that node's global position, network configuration, etc.

Q: Why do I get ``NET::ERR_CERT_INVALID`` when loading the Ursula node status page?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The status page uses a self-signed certificate, but browsers don’t like it.
You can usually proceed to the page anyway. If not, try using a different browser.

Q: What types of Ethereum web3 node providers do you support?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* IPC Socket-based JSON-RPC server e.g. ``ipc:///home/<username>/.ethereum/geth.ipc``
* HTTP(S)-based JSON-RPC server e.g. ``http://<host>``, ``https://<host>``
* Websocket(Secure)-based JSON-RPC server e.g. ``ws://<host>:8080``, ``wss://<host>:8080``

Q: How does my node choose what price to use for transactions? Can I control this?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When sending a transaction, your node automatically chooses the gas price
using a `gas strategy <https://web3py.readthedocs.io/en/stable/gas_price.html>`_.

We currently offer three types of gas strategies,
based on the approximate confirmation time:

- ``slow``: Confirmation expected within **one hour**.
- ``medium``: Confirmation expected within **five minutes**.
- ``fast``: Confirmation expected within **one minute**.

Note that the times are an approximation, and the confirmation time may vary
when gas prices experience more volatility.

In such situations, transactions may not be mined within the expected time.
However, your node keeps track of the transactions and is capable of automatically
sending replacement transactions to adjust to a scenario with new prices.
In any case, we recommend that you monitor your node to be sure that the
transactions are being sent and confirmed correctly.

You can set a gas strategy using the Ursula configuration command.
For example, the following command sets the ``medium`` gas strategy:

.. code:: bash

    (nucypher)$ nucypher ursula config --gas-strategy medium


There's an additional, advanced control mechanism for limiting the maximum
gas price that your node can spend.  The ``--max-gas-price`` flag can be used to configure the limit in `gwei`.
This is complementary to the gas strategy that you may have configured.

.. code:: bash

    (nucypher)$ nucypher ursula config --max-gas-price 50

.. warning::

    If you set a maximum limit and gas prices remain higher
    than that limit, it's possible that your node will not get
    the transaction included in the blockchain.

.. warning::

    The maximum gas price limit is an experimental feature and may be changed
    or removed in the future.


Threshold Network Merger
------------------------

*Questions related to the merger with the Keep Network to launch the Threshold Network* (More info `here <https://blog.threshold.network/threshold-launch/>`_).

Q: What are the benefits of the network merger between NU and Keep?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See `Twitter thread <https://twitter.com/NuCypher/status/1478478558280527885?s=20&t=sUDMynarfjnLv8blAxR5Yw>`_.

Q: What is the Threshold Network website
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

https://threshold.network

Q: Is this NuCypher Discord server still in use?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The community has migrated to the `Threshold Discord <https://discord.gg/Threshold>`_ and the NuCypher Discord server has been set to read-only.


Q: What is the T token address?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

T is the work token for the Threshold Network. See https://etherscan.io/address/0xcdf7028ceab81fa0c6971208e83fa7872994bee5.

Q: How do I see my T tokens in my Metamask wallet?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Input the T token address, ``0xCdF7028ceAB81fA0C6971208e83fa7872994beE5``, in your wallet.

Q: How do you upgrade NU to T?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Via the `Threshold Dashboard <https://dashboard.threshold.network/upgrade/NU>`_.

Q: How do you downgrade T to NU?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can downgrade T back to NU through the smart contract directly.

However, ONLY to the original upgrade address can perform the downgrade, and only to the maximum of the original amount
that was upgraded (downgrading is not fungible).


Q: Is it possible to upgrade KEEP -> T then downgrade T -> NU?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

T can only be converted back to the original wrapped token.


Q: What is the NU → T VendingMachine address?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

https://etherscan.io/address/0x1cca7e410ee41739792ea0a24e00349dd247680e

Q: What is the NU to T conversion ratio?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

1 NU = 3.259242493160746 T.

Q: Will the conversion rate be fixed regardless of NU and T price?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes. The vending machine is perpetual and the ratio is static.

Q: Will KEEP / NU be delisted in favor of T?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The token to participate in staking and governance will be T.  NU and KEEP held on exchanges
will be subject to exchanges' terms for the upgrade.  We can not speculate on when CEXs will
list or delist specific assets but the ultimate goal is for everyone who owns NU or KEEP
to eventually upgrade to T so that they can participate in the Threshold Network.

Q: How do I use the Vending Machine contract directly?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See the `Vending Machine Documentation <https://github.com/threshold-network/solidity-contracts/blob/main/docs/rfc-2-vending-machine.adoc>`_.

Q: How do I stake T?
~~~~~~~~~~~~~~~~~~~~

Via the `Threshold Dashboard Staking UI <https://dashboard.threshold.network/staking>`_.

Q: What happens if my stake is/was locked?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unless a stake is subject to vesting associated with a legal agreement (e.g. SAFT 2 purchaser, team etc.) it will be immediately withdrawable. These Stakers can:

#. Withdraw any existing unlocked stake: https://stake.nucypher.network/manage/withdraw
#. Upgrade the unlocked NU to T: https://dashboard.threshold.network/upgrade/nu
#. Stake the upgraded T: https://dashboard.threshold.network/staking

For **locked** stakes, an adapter will allow these stakes to operate nodes on the Threshold Network and receive T token rewards. These Stakers can
migrate existing locked stakes from NU to Threshold via https://stake.nucypher.network/manage/stake. Once these stakes expire and the locked tokens become unlocked / liquid,
they can be upgraded to T and staked as T.

Q: Is there a minimum stake size?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The current minimum stake size for running a PRE node is 40,000 T but is tunable via governance.

Q: What happened to the existing NU contracts after the merge?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

They continue to exist on the Ethereum mainnet but most of the functionality is disabled.

Q: When was NU inflation halted?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Thursday, December 30th after the execution
of NuCypher DAO proposal `#2 <https://client.aragon.org/#/nucypherdao/0x61950d573c741ca10ee6815de11bcbe7e60a0f10/vote/2/>`_

Q: Can I still withdraw my ETH from WorkLock?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It is withdrawable. The ``StakingEscrow`` contract still contains the code needed for anyone who still has ETH locked in Worklock.
