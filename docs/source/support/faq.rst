==========================
Frequently Asked Questions
==========================

Network-Related Questions
-------------------------

*These are questions related to how the NuCypher network works.*

We assume familiarity with the network characters "**Alice**," "**Bob**," "**Ursula**," and "**Enrico**."

To briefly review, **Alice** is the *data owner*. She wants to share some data with **Bob**, *the data recipient*.

**Enrico** *encrypts data on behalf of Alice* to produce the ciphertext (more specifically a MessageKit). In many cases (though not all!), **Enrico** is controlled by **Alice**.

**Ursula** serves as the "*proxy*" in this proxy re-encryption scheme and *re-encrypts the ciphertext encrypted under Alice's key to a ciphertext that will be decryptable under Bob's key*.

|
**Q: How much trust do we place in Ursula, the proxy?**


Ursulas are “semi-trusted” in the sense that Alice must trust Ursula to revoke a policy once it expires or if instructed to do so (by Alice). We also must trust Ursula to be responsive and perform the re-encryption correctly so that Bob can access the data. 

|
**Q: Who pays Ursula? How is it done?**

Currently, Alice pays Ursula (since Ursula is doing work for Alice). Alice pays an ETH deposit into the PolicyManager contract when granting.

(However, we do imagine Bob paying in some models!)

|
**Q: How do we verify that Ursula has performed the re-encryption correctly?**

Every time an Ursula produces a re-encryption, she computes a zero-knowledge proof that proves that the re-encryption she just performed is correct, without disclosing any kind of secret information. This  correctness proof is publicly verifiable, so in the event someone detects incorrect re-encryptions coming from an Ursula, these faulty proofs can be sent to a smart contract that will slash the stake associated with that Ursula. However, in a normal scenario, with Ursula working correctly, there’s no need for correctness proofs to be submitted on-chain.

|
**Q: How much trust do we place in Enrico?**

As mentioned above, Enrico is often (not always!) controlled by Alice. Enrico must be trusted to perform the encryption correctly and to not disclose the secret key. However, these things are out of our (cryptographic) control.

Additionally, Alice can decrypt (and thus read) anything encrypted by Enrico.

|
**Q: Who is the Staker in this narrative? Is it Alice or Ursula?**

The Staker can be thought of as a fiduciary administrator that holds NU and collects rewards.

Typically, but not always, Ursula and the Staker are the same party. Recall that Ursula is only “valid” (i.e. will be selected for work and able to earn inflation rewards) if she’s bonded to a Staker.

|
**Q: What kind of token is NU?**

NU is an implementation of the ERC20 standard deployed onto the Ethereum blockchain.

|
**Q: Why have the Staker and Ursula been split?**

We split them so that the Staker can hold NU offline in a hardware wallet.

|
**Q: What currency does Alice use to pay for re-encryptions? What currency does Ursula stake in (assuming Ursula is also the Staker)?**

Alice pays for re-encryptions in Ether. Ursula stakes in NU. Ursula will collect policy rewards in ETH and inflation rewards in NU.

What are the two streams of income Ursula can receive?

Inflation Rewards (NU) and Policy Rewards (ETH). We will soon refer to Policy Rewards as “Fees” to avoid confusion.

|
**Q: Why do you have a mix of NU and ETH?**

It’s much more convenient for Alice to simply carry ETH. If she has to acquire NU also, it sets a much higher barrier to entry.

|
**Q: How are Policy Rewards (ETH) determined?**

The reward is calculated with Confirm Activity taking into account the number of policies Ursula is enforcing.

|
**Q: How many Ursulas per period collect Inflation rewards (NU)?**

Every Ursula that is “online” and “available” will receive a cut based on the size of their stake.

|
**Q: How long is a period?**

1 period equals 24 hours. Periods begin at midnight UTC.

|
**Q: Where are Bob’s requests handled?**

Bob’s requests are handled off-chain.

|
**Q: Why are Bob’s requests handled off-chain?**

It allows for a very small/lightweight Bob.


Setup-Related Questions
-----------------------

*These are questions related to setting up the NuCypher network on your machine.*

|
**Q: What are the recommended specifications for running a nucypher node?**

Worker nodes need to run ``nucypher`` and a local ethereum node. In total, you will
require at least 4GB for RAM. Nodes also need 24/7 uptime and a static, public IPv4 address.

For ``nucypher`` specific requirements, see `System Requirements and Dependencies <https://docs.nucypher.com/en/latest/guides/installation_guide.html#system-requirements-and-dependencies/>`_.

|
**Q: What is the network name for Incentivized Testnet?**

The network name is ``cassandra``.

|
**Q: Can my Staker and Worker address be the same?**

Technically, yes, but it is not recommended. The accounts have different security considerations - the staker address
is high-value and can be a hardware wallet (with NU and ETH) that performs stake management while the worker
address is low-value and needs to remain unlocked while running (software wallet with ETH) since it
is used by an Ursula node.

You should stake with one address and set the worker to be a different address. Subsequently, you can bond
the worker address to the stake.

|
**Q: Is there a guide for Windows?**

Our guide is intended for Linux - we do not officially support Windows.

|
**Q: Where is my Ursula config path?**

On Ubuntu/Debian - ``$HOME/.local/share/nucypher/ursula.json``

|
**Q: What is the difference between Standard Installation and Development Installation?**

The Development Installation is only needed for developing with ``nucypher``. You don't need to use
it unless you plan to make changes to the codebase. If you are simply staking/running a node, you
only need the Standard Installation

|
**Q: How do I know that my node is set up correctly?**

This is **ONLY** a heuristic to ensure that your node is running correctly, it doesn't guarantee your node is setup correctly: 

    #. Ensure that your Ursula node is up and running (logs/terminal):

       .. code::

            Starting Ursula on xxx.xxx.xxx.xxx:9151
            Connecting to cassandra
            Working ~ Keep Ursula Online!

    #. Ensure that your node uses the correct IP address and can be accessed via port 9151 from an outside
       connection eg. cell phone, other computer etc. by navigating to: ``https://<node_ip>:9151/status``

    #. Ensure that your worker is bonded with your staker - ``nucypher stake list`` and check that
       *Worker* is set correctly i.e. not ``0x0000``.

    #. Run the following command and ensure that the various settings are correct::

        nucypher status stakers
        >    --provider <your_geth_provider>
        >    --network cassandra
        >    --staking-address <your_staker_address>

    #. Ensure that your node is listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).

|
**Q: What's the best way to run Ursula in the background?**

Either through :ref:`Docker <run-ursula-with-docker>`
or `systemd <https://docs.nucypher.com/en/latest/guides/installation_guide.html#systemd-service-installation>`_.

|
**Q: When installing on Docker, what do I input for <NETWORK NAME>?**

For the *“Come and Stake It”* incentivized testnet, the network name is ``cassandra``.

|
**Q: How can I check my current staking rewards?**

Run::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
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

|
**Q: How can I observe the settings (re-staking, winding down) for my stake?**

Run::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>

|
**Q: Can I extend the duration of my existing stake?**

Yes, via the :ref:`prolong <staking-prolong>` command.

|
**Q: How can I reuse an Ursula that was connected to the previous version of the testnet?**

#. Run ``nucypher ursula destroy`` to destroy the current configuration.
#. Repeat all of the steps with the new tokens in the :ref:`staking-guide`.
#. Run ``nucypher ursula init`` per the :ref:`ursula-config-guide`.

|
**Q: What is a fleet state?**

A symbol which represents your node's view of the network. It is just a
graphic checksum, so a minor change in the fleet (e.g., a new node joins, a node disappears, etc.)
will produce a completely different fleet state symbol. A node can have a
different fleet state than others, which may indicate that a different number of peers are accessible from
that node's global position, network configuration, etc..

|
**Q: Why do I get `NET::ERR_CERT_INVALID` when loading the Ursula node status page?**

The status page uses a self-signed certificate, but browsers don’t like it.
You can usually proceed to the page anyway. If not, try using a different browser.

|
**Q: This all seems too complex for me, can I still participate in some way?**

We highly recommend delegating to an experienced staker rather than doing it yourself, if
you are not super familiar with running nodes for other networks.

|
**Q: Why is my node is labelled as Idle in the status monitor?**

Your node is `Idle` because it has never confirmed activity. Likely, your worker address does not have any
ETH to use for transaction gas.

|
**Q: The status of my node on the status monitor seems incorrect?**

Check when last your node confirmed activity by running::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>

If everything looks fine, the status monitor probably just needs some time to connect to the node again to update the
node's status.

