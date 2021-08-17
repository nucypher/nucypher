==========================
Frequently Asked Questions
==========================

The answers in the FAQ regularly reference the network characters "**Alice**," "**Bob**," "**Ursula**," and "**Enrico**." For a more in-depth introduction to each character, head over to :ref:`character-concepts`.

**Alice** is the *data owner*. She wants to share some data with **Bob**, *the data recipient*.

**Enrico** *encrypts data on behalf of Alice* to produce the ciphertext (more specifically a MessageKit). In many cases (though not all!), **Enrico** is controlled by **Alice**.

**Ursula** serves as the "*proxy*" in this proxy re-encryption scheme and *re-encrypts the ciphertext encrypted under Alice's key to a ciphertext that will be decryptable under Bob's key*.




General
-------

.. _faq-testnet:

Q: What is the network name for NuCypher's testnet?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NuCypher currently has two testnets available, each of them with different goals:

* ``lynx``: Public Long-Term Support testnet, intended as a stable playground for network users (e.g., Alices wishing to create sharing policies). Running on Ethereum Goerli testnet.
* ``ibex``: Public testnet, intended as a playground for stakers and node operators (e.g., learning how to create and manage stakes, setting up a node), as well as for internal development purposes. Running on Ethereun Rinkeby testnet.

Q: What is a period and how long is it?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the NuCypher protocol, a Period is the minimum unit of time. This applies to sharing policy durations, and
also corresponds to the frequency that Workers must make an on-chain commitment to being online and available
to provide service.

1 period is 7 days, and periods always start on Thursdays at midnight UTC.

At Network launch, 1 period was 24 hours, but this was updated by a NuCypher DAO proposal to be
7 days (see :doc:`/architecture/periods`).


Using the Network
-----------------

*These are questions related to how the NuCypher network works.*

Q: How do I know if NuCypher is a good fit for my use case?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A centralized approach to access control means users are forced to trust the system(s) with the plaintext version of
their private data, and usually are given little insight into who exactly they are trusting. NuCypher’s decentralized
access control system offers developers, and their users, a departure from this opaque and trust-dependent paradigm.
When integrated, `nucypher` enables end-to-end encrypted data sharing workflows within applications – but
crucially, without sacrificing scalability, redundancy or performance – and applicable to data payloads of
any form, size, structure, sensitivity or production cadence. Users enjoy the same sharing powers they
currently take for granted, but are **not** obliged to trust the developers of the application or
third-party access control services (e.g. centralized servers or key management systems) with their data.

Q: How is NuCypher different from more traditional public key infrastructure (PKI)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For an in-depth analysis of this topic, see our blog post entitled "`Three things that NuCypher's "Ursula" can do that vanilla public-key cryptography can't <https://blog.nucypher.com/why-use-nucyphers-ursula-instead-of-traditional-public-key-cryptography/>`_".

Q: How much trust do we place in Ursula, the proxy?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ursulas are “semi-trusted” in the sense that Alice must trust Ursula to revoke a policy once it expires or if instructed to do so (by Alice). Alice and Bob also trust Ursula to be responsive and perform the re-encryption correctly so that Bob can access the data. Importantly, Ursulas are not trusted with access to any underlying plaintext.

Q: How do we verify that Ursula has performed the re-encryption correctly?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every time an Ursula produces a re-encryption, she computes a zero-knowledge proof that proves that the re-encryption she just performed is correct, without disclosing any kind of secret information. This  correctness proof is publicly verifiable, so in the event someone detects incorrect re-encryptions coming from an Ursula, these faulty proofs can be sent to a smart contract that will slash the stake associated with that Ursula. However, in a normal scenario, with Ursula working correctly, there’s no need for correctness proofs to be submitted on-chain.

Q: How much trust do we place in Enrico?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enrico is often (not always!) controlled by Alice. Enrico must be trusted to perform the encryption correctly and to not disclose the secret key. However, these things are out of our (cryptographic) control.
Additionally, Alice can decrypt (and thus read) anything encrypted by Enrico.

Q: Who is the Staker in this narrative? Is it Alice or Ursula?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The Staker can be thought of as a fiduciary administrator that holds NU and collects rewards.
Ursula performs work on behalf of the Staker: recall that Ursula is only “valid” (i.e. will be selected for work and able to earn inflation rewards) if she’s bonded to a Staker.

Q: Does Alice or Bob need NU to use the network? Who pays Ursula? How is it done?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Neither Alice nor Bob need NU to use the network - Stakers require NU to run Ursulas on the network. However, Alice pays Ursulas for re-encryptions via an ETH deposit to the PolicyManager contract at the point of granting access to Bob. Payment models are an area of active research for the NuCypher protocol, including the prospect of Bob independently paying in ETH for all or some component of the work performed by Ursula.

Q: How much does Alice pay?
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Alice provides an upfront deposit that covers the entirety of the sharing policy's duration (in periods), for all the Ursulas required to service the policy. Currently, Ursulas may choose a discretionary payment rate per period, which Alice discovers on an Ursula-by-Ursula basis by querying public network contracts. In the early stages of the network, both Alice and Ursula must settle on a rate which falls within a fixed, universal range, enforced by the PolicyManager contract.

Q: What currency does Ursula stake in (assuming Ursula is also the Staker)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Ursula stakes in NU, receives policy fees in ETH, and receives inflation rewards in NU.

Q: Why do you have a mix of NU and ETH?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It’s much more convenient for Alice to simply carry ETH. If she has to acquire NU also, it sets a much higher barrier to entry.
Additionally, since NU is an ERC20 token, using it for payment instead of ETH offers no advantages.

Q: Where are Bobs’ requests handled?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bobs' requests are handled off-chain.

Q: Why are Bobs' requests handled off-chain?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It allows for a very small/lightweight Bob.

Q: Why can't my users reuse their Ethereum wallet keys when creating a sharing policy?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Avoiding key reuse is a strong defense-in-depth measure against cryptographic and software flaws. While it is
possible to use your ETH keys in `nucypher`, we strongly advise against such a practice. It is best to keep these
sets of keys separate.

Q: How can I get help integrating nucypher into my application?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :doc:`/application_development/getting_started`. To chat directly with our team, please join our `Discord <http://discord.nucypher.com>`_.

Q: How do I integrate nucypher if my application is not written in Python?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Nucypher also provides REST-like HTTP endpoints for working with characters. See :ref:`character-control-guide`.


Running a Node
--------------

*These are questions related to running a node on the NuCypher network.*

Q: What kind of token is NU?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NU is an implementation of the ERC20 standard deployed onto the Ethereum blockchain.

Q: What are the two streams of income Ursula can receive?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Inflation Rewards (NU) and Policy Fees (ETH).

Q: How are Policy Fees (ETH) determined?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The amount of fees a staker can earn in a given period is determined by multiple factors,
including (1) the minimum fee rate set by the staker,
(2) the number of active policies issued by users of the network to that staker,
and (3) whether the staker has previously committed to being available for that period.
See :doc:`/architecture/rewards_and_service_fees` for details.

Q: How many Ursulas per period collect Inflation rewards (NU)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every Ursula that is “online” and “available” will receive a cut based on the size of their stake proportional to the overall NU staked in the network and augmented by a time coefficient based on their remaining stake duration.

Q: How/Where can I acquire NU tokens?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The initial distribution of NU was done via the "*WorkLock*" mechanism developed by NuCypher -
more information is available in our `original blog post <https://blog.nucypher.com/the-worklock/>`_ and :ref:`worklock-guide`.

Participation in WorkLock is now closed, but since NU is an ERC-20 token, it can be purchased through exchanges.

Q: When/Why does a node operator need to use ``mint`` command?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The period following stake termination or later, but before withdrawing escrowed tokens. Each node on the NuCypher network sends per period commitment transactions signalling continued commitment to providing service, and to calculation of NU rewards for prior periods ("minting"). At the final period of a stake, automatic minting will stop and intervention is required to complete the final minting calculation by calling ``mint`` manually.

Q: What are the recommended specifications for running a nucypher node?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`ursula-config-guide`.

Q: How do I set up a network node?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See :ref:`running-a-node`.

Q: Is there a guide for Windows?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Our guide is intended for Linux - we do not officially support Windows.

Q: How computationally expensive is performing re-encryptions likely to be?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A re-encryption operation is very lightweight (in the order of milliseconds) and is comparable to computing an ECDSA signature.

Q: Can my Staker and Worker address be the same?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Technically, yes, but it is not recommended. The accounts have different security considerations - the staker address
is high-value and can be a hardware wallet (with NU and ETH) that performs stake management while the worker
address is low-value and needs to remain unlocked while running (software wallet with ETH) since it
is used by an Ursula node.

You should stake with one address and set the worker to be a different address. Subsequently, you can bond
the worker address to the stake.

Q: How do I maximize the inflation-based rewards I will receive?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    * Lock your stake for a year or more - stakes with tokens locked for a year or more will be afforded the maximum time coefficient for the calculation of inflation rewards - see :ref:`ursula-generates-staking-rewards`.
    * Enable :ref:`sub-stake-restaking` to relock inflation rewards and increase your stake size and consequently your proportion of future inflation rewards
    * Disable :ref:`sub-stake-winddown` to maintain locked stake duration

Q: Where is my Ursula config path?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Default configuration and logging paths can be displayed using the command line:

Configuration path - ``nucypher --config-path``
Default logging path - ``nucypher --logging-path``

On Ubuntu/Debian the default ursula configuration path is``$HOME/.local/share/nucypher/ursula.json``,
however if you have more than one ursula configuration, the filename will include the checksum address:
``$HOME/.local/share/nucypher/ursula-0xdeadbeef.json``.

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
       connection eg. cell phone, other computer etc. by navigating to: ``https://<node_ip>:9151/status``

    #. Ensure that your worker is bonded with your staker - ``nucypher stake list`` and check that
       *Worker* is not ``0x0000``.

    #. Run the following command and ensure that the various settings are correct::

        nucypher status stakers
        >    --provider <YOUR PROVIDER URI>
        >    --network <NETWORK>
        >    --staking-address <YOUR STAKER ADDRESS>

    #. Ensure that your node is listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).

Q: What's the best way to run Ursula in the background?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using docker :ref:`Docker <run-ursula-with-docker>`

Q: When installing on Docker, what do I input for <NETWORK NAME>?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``mainnet`` if you want to interact with the main NuCypher network,
and either ``lynx`` or ``ibex`` in case you want to use one of our testnets.
Go :ref:`here <faq-testnet>` to read more about the difference between both testnets.

Q: How can I check for currently available staking rewards?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run::

    nucypher status stakers
    >    --provider <YOUR PROVIDER URI>
    >    --network <NETWORK>
    >    --staking-address <YOUR STAKER ADDRESS>

Note that a minimum of two periods must elapse before rewards will be delivered to your wallet. For example, say we
are in Period 5 when you start staking:

- Period 5: You deposit stake and initiate a worker
- Period 5: Your worker calls ``commitToNextPeriod()`` in order to receive work for the next period
- Period 6: Your worker successfully performs the work
- Period 7: Your worker receives rewards for the work completed in the previous period

.. note::

    :ref:`Restaking <sub-stake-restaking>` is enabled by
    default, so NU inflation rewards are automatically restaked for you, and will be reflected in
    the ``Staked`` value of the above command.

Q: How can I observe the settings (re-staking, winding down) for my stake?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run::

    nucypher status stakers
    >    --provider <YOUR PROVIDER URI>
    >    --network <NETWORK>
    >    --staking-address <YOUR STAKER ADDRESS>


Q: Can I extend the duration of my existing stake?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Yes, via the :ref:`prolong <staking-prolong>` command.

Q: How can I reuse an Ursula that was connected to the previous version of the testnet?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

#. Run ``nucypher ursula destroy`` to destroy the current configuration.
#. Repeat all of the steps with the new tokens in the :ref:`staking-guide`.
#. Run ``nucypher ursula init`` per the :ref:`ursula-config-guide`.

Q: What is a fleet state?
~~~~~~~~~~~~~~~~~~~~~~~~~

A symbol which represents your node's view of the network. It is just a
graphic checksum, so a minor change in the fleet (e.g., a new node joins, a node disappears, etc.)
will produce a completely different fleet state symbol. A node can have a
different fleet state than others, which may indicate that a different number of peers are accessible from
that node's global position, network configuration, etc.

Q: Why do I get ``NET::ERR_CERT_INVALID`` when loading the Ursula node status page?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The status page uses a self-signed certificate, but browsers don’t like it.
You can usually proceed to the page anyway. If not, try using a different browser.

Q: This all seems too complex for me, can I still participate in some way?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We highly recommend delegating to an experienced staker rather than doing it yourself, if
you are not super familiar with running nodes for other networks.
See :ref:`node-providers`.

Q: Why is my node is labelled as "*Idle*" in the status monitor?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Your node is `Idle` because it has never made a commitment. Likely, your worker address does not have any
ETH to use for transaction gas.

Q: The status of my node on the status monitor seems incorrect?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check when last your node made a commitment by running::

    nucypher status stakers
    >    --provider <YOUR PROVIDER URI>
    >    --network <NETWORK>
    >    --staking-address <YOUR STAKER ADDRESS>

If everything looks fine, the status monitor probably just needs some time to connect to the node again to update the
node's status.

Q: What types of Ethereum web3 node providers do you support?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* IPC Socket-based JSON-RPC server e.g. ``ipc:///home/<username>/.ethereum/geth.ipc``
* HTTP(S)-based JSON-RPC server e.g. ``http://<host>``, ``https://<host>``
* Websocket(Secure)-based JSON-RPC server e.g. ``ws://<host>:8080``, ``wss://<host>:8080``


Q: Is there a difference between delegating staking and running a node yourself?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Delegating stake and/or work to a 3rd party is a good option for those who are not confident with the technicals
of staking and running a node and/or are concerned about gas costs relative to stake size (e.g. small stakers).

If you are comfortable with technical requirements of staking or wish to implement a sophisticated staking configuration
(e.g. restake toggles,  stake extensions, sub-stakes, adding stake, etc.) it may not be the right option.


Q: How does my worker node choose what price to use for transactions? Can I control this?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When sending a transaction, your worker node automatically chooses the gas price
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
gas price that your node can spend.  The ``--max-gas-price`` flag can be used to configure limit in `gwei`.
This is complementary to the gas strategy that you may have configured.

.. code:: bash

    (nucypher)$ nucypher ursula config --max-gas-price 50

.. warning::

    If you set a maximum limit and gas prices remain higher
    than that limit, it's possible that your node will not get
    the commitment transaction included in the blockchain.
    This implies that you can miss some rewards.

.. warning::

    The maximum gas price limit is an experimental feature and may be changed
    or removed in the future.
