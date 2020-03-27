==========================
Frequently Asked Questions
==========================

The answers in the FAQ regularly reference the network characters "**Alice**," "**Bob**," "**Ursula**," and "**Enrico**." For a more in-depth introduction to each character, head over to :ref:`character-concepts`.

**Alice** is the *data owner*. She wants to share some data with **Bob**, *the data recipient*.

**Enrico** *encrypts data on behalf of Alice* to produce the ciphertext (more specifically a MessageKit). In many cases (though not all!), **Enrico** is controlled by **Alice**.

**Ursula** serves as the "*proxy*" in this proxy re-encryption scheme and *re-encrypts the ciphertext encrypted under Alice's key to a ciphertext that will be decryptable under Bob's key*.




General
-------

Q: What is the network name for Incentivized Testnet?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The network name for incentivized testnet is ``gemini``.

Q: How long is a period?
~~~~~~~~~~~~~~~~~~~~~~~~

1 period is 24 hours. Periods begin at midnight UTC.




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

Ursula stakes in NU, receives policy rewards in ETH, and receives inflation rewards in NU.

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

See :ref:`application-development`. To chat directly with our team, please join our `Discord <http://discord.nucypher.com>`_.

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

Inflation Rewards (NU) and Policy Rewards (ETH). We will soon refer to Policy Rewards as “Fees” to avoid confusion.

Q: How are Policy Rewards (ETH) determined?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The reward is calculated with Confirm Activity taking into account the number of policies Ursula is enforcing.

Q: How many Ursulas per period collect Inflation rewards (NU)?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Every Ursula that is “online” and “available” will receive a cut based on the size of their stake proportional to the overall NU staked in the network and augmented by a time coefficient based on their remaining stake duration.

Q: How/Where can I acquire NU tokens?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NU tokens can be acquired via the "*WorkLock*" mechanism developed by NuCypher - more information is available in our `original blog post <https://blog.nucypher.com/the-worklock/>`_ and :ref:`worklock-guide`.

Q: What are the recommended specifications for running a nucypher node?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Worker nodes need to run ``nucypher`` and a local ethereum node. In total, you will
require at least 4GB for RAM. Nodes also need 24/7 uptime and a static, public IPv4 address.

For ``nucypher`` specific requirements, see `System Requirements and Dependencies <https://docs.nucypher.com/en/latest/guides/installation_guide.html#system-requirements-and-dependencies/>`_.

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

    * Lock your stake for a year or more - stakes with tokens locked for a year or more will be afforded the maximum time coefficient for the calculation of inflation rewards - see `Ursula Generates Staking Rewards <https://docs.nucypher.com/en/latest/architecture/contracts.html#ursula-generates-staking-rewards>`_
    * Enable :ref:`sub-stake-restaking` to relock inflation rewards and increase your stake size and consequently your proportion of future inflation rewards
    * Disable :ref:`sub-stake-winddown` to maintain locked stake duration

Q: Where is my Ursula config path?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

On Ubuntu/Debian - ``$HOME/.local/share/nucypher/ursula.json``

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
            Connecting to gemini
            Working ~ Keep Ursula Online!

    #. Ensure that your node uses the correct IP address and can be accessed via port 9151 from an outside
       connection eg. cell phone, other computer etc. by navigating to: ``https://<node_ip>:9151/status``

    #. Ensure that your worker is bonded with your staker - ``nucypher stake list`` and check that
       *Worker* is set correctly i.e. not ``0x0000``.

    #. Run the following command and ensure that the various settings are correct::

        nucypher status stakers
        >    --provider <your_geth_provider>
        >    --network gemini
        >    --staking-address <your_staker_address>

    #. Ensure that your node is listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).

Q: What's the best way to run Ursula in the background?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Either through :ref:`Docker <run-ursula-with-docker>`
or `systemd <https://docs.nucypher.com/en/latest/guides/installation_guide.html#systemd-service-installation>`_.

Q: When installing on Docker, what do I input for <NETWORK NAME>?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For the *“Come and Stake It”* incentivized testnet, the network name is ``gemini``.

Q: How can I check for currently available staking rewards?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network gemini
    >    --staking-address <your_staker_address>

Note that a minimum of two periods must elapse before rewards will be delivered to your wallet. For example, say we
are in Period 5 when you start staking:

- Period 5: You deposit stake and initiate a worker
- Period 5: Your worker calls ``confirmActivity()`` in order to receive work for the next period
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
    >    --provider <your_geth_provider>
    >    --network gemini
    >    --staking-address <your_staker_address>


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
that node's global position, network configuration, etc..

Q: Why do I get `NET::ERR_CERT_INVALID` when loading the Ursula node status page?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The status page uses a self-signed certificate, but browsers don’t like it.
You can usually proceed to the page anyway. If not, try using a different browser.

Q: This all seems too complex for me, can I still participate in some way?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We highly recommend delegating to an experienced staker rather than doing it yourself, if
you are not super familiar with running nodes for other networks.

Q: Why is my node is labelled as "*Idle*" in the status monitor?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Your node is `Idle` because it has never confirmed activity. Likely, your worker address does not have any
ETH to use for transaction gas.

Q: The status of my node on the status monitor seems incorrect?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Check when last your node confirmed activity by running::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network gemini
    >    --staking-address <your_staker_address>

If everything looks fine, the status monitor probably just needs some time to connect to the node again to update the
node's status.
