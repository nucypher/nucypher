==========================
Frequently Asked Questions
==========================

What are the recommended specifications for running a nucypher node?
--------------------------------------------------------------------

Worker nodes need to run ``nucypher`` and a local ethereum node. In total, you will
require at least 4GB for RAM. Nodes also need 24/7 uptime and a static, public IPv4 address.

For ``nucypher`` specific requirements, see `System Requirements and Dependencies <https://docs.nucypher.com/en/latest/guides/installation_guide.html#system-requirements-and-dependencies/>`_.


What is the network name for Incentivized Testnet?
--------------------------------------------------

The network name is ``cassandra``.


How long is a period?
---------------------

1 period equals 24 hours. Periods begin at midnight UTC.


Can my Staker and Worker address be the same?
---------------------------------------------

Technically, yes, but it is not recommended. The accounts have different security considerations - the staker address
is high-value and can be a hardware wallet (with NU and ETH) that performs stake management while the worker
address is low-value and needs to remain unlocked while running (software wallet with ETH) since it
is used by an Ursula node.

You should stake with one address and set the worker to be a different address. Subsequently, you can bond
the worker address to the stake.


Is there a guide for Windows?
-----------------------------

Our guide is intended for Linux - we do not officially support Windows.


Where is my Ursula config path?
-------------------------------

On Ubuntu/Debian - ``$HOME/.local/share/nucypher/ursula.json``


What is the difference between Standard Installation and Development Installation?
----------------------------------------------------------------------------------

The Development Installation is only needed for developing with ``nucypher``. You don't need to use
it unless you plan to make changes to the codebase. If you are simply staking/running a node, you
only need the Standard Installation


How do I know that my node is set up correctly?
-----------------------------------------------

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


What's the best way to run Ursula in the background?
----------------------------------------------------

Either through :ref:`Docker <run-ursula-with-docker>`
or `systemd <https://docs.nucypher.com/en/latest/guides/installation_guide.html#systemd-service-installation>`_.


When installing on Docker, what do I input for <NETWORK NAME>?
---------------------------------------------------------------

For the *“Come and Stake It”* incentivized testnet, the network name is ``cassandra``.


How can I check my current staking rewards?
-------------------------------------------

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


How can I observe the settings (re-staking, winding down) for my stake?
-----------------------------------------------------------------------

Run::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>


Can I extend the duration of my existing stake?
--------------------------------------------------------------

Yes, via the :ref:`prolong <staking-prolong>` command.


How can I reuse an Ursula that was connected to the previous version of the testnet?
------------------------------------------------------------------------------------

#. Run ``nucypher ursula destroy`` to destroy the current configuration.
#. Repeat all of the steps with the new tokens in the :ref:`staking-guide`.
#. Run ``nucypher ursula init`` per the :ref:`ursula-config-guide`.


What is a fleet state?
----------------------

A symbol which represents your node's view of the network. It is just a
graphic checksum, so a minor change in the fleet (e.g., a new node joins, a node disappears, etc.)
will produce a completely different fleet state symbol. A node can have a
different fleet state than others, which may indicate that a different number of peers are accessible from
that node's global position, network configuration, etc..


Why do I get `NET::ERR_CERT_INVALID` when loading the Ursula node status page?
------------------------------------------------------------------------------

The status page uses a self-signed certificate, but browsers don’t like it.
You can usually proceed to the page anyway. If not, try using a different browser.


This all seems too complex for me, can I still participate in some way?
-----------------------------------------------------------------------

We highly recommend delegating to an experienced staker rather than doing it yourself, if
you are not super familiar with running nodes for other networks.


Why is my node is labelled as Idle in the status monitor?
---------------------------------------------------------

Your node is `Idle` because it has never confirmed activity. Likely, your worker address does not have any
ETH to use for transaction gas.


The status of my node on the status monitor seems incorrect?
------------------------------------------------------------

Check when last your node confirmed activity by running::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>

If everything looks fine, the status monitor probably just needs some time to connect to the node again to update the
node's status.

