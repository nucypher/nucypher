==========================
Frequently Asked Questions
==========================

What are the recommended specifications for running a nucypher node?
-------------------------------------------------------------------

Worker nodes need to run ``nucypher`` and a local ethereum node. In total, you will
require at 4GB for RAM. Nodes also need 24/7 uptime and a static, public IPv4 address.

For ``nucypher`` specific requirements, see `System Requirements and Dependencies <https://docs.nucypher.com/en/latest/guides/installation_guide.html#system-requirements-and-dependencies/>`_.


What is the network name for Incentivized Testnet?
--------------------------------------------------

The network name is ``cassandra``.


How long is a period?
---------------------

1 period equals 24 hours. Periods begin at midnight UTC time.


What's the difference between staker address and worker address? Can they be the same?
--------------------------------------------------------------------------------------

Technically, yes, but it is not recommended. The accounts have different security considerations - the staker address can be a high-value hardware wallet
(staker with NU) that performs stake management while the worker is low-value and needs to remain
unlocked while running (software wallet) since it used by an Ursula node.

You should stake with one address and set the worker to be a different address. Subsequently, you can bond
the worker address to the stake.


Is there a guide for Windows?
-----------------------------

Our guide is intended for Linux - we do not officially support Windows.


Where is my Ursula config path?
-------------------------------

On Linux - ``$HOME/.local/share/nucypher/ursula.json``


What is the difference between Standard Installation and Development Installation?
----------------------------------------------------------------------------------

The Development Installation is only needed for developing with ``nucypher``. You don't need to use
it unless you plan to make changes to the codebase. If you are simply staking/running a node, you
only need the Standard Installation


How do I know that my node is setup correctly?
----------------------------------------------

This is **ONLY** a heuristic to ensure that your node is running correctly, it doesn't guarantee your node is setup correctly: 

    #. Ensure that your Ursula node is up and running (logs/terminal):

       .. code::

            Starting Ursula on xxx.xxx.xxx.xxx:9151
            Connecting to cassandra
            Working ~ Keep Ursula Online!

    #. Ensure that your node uses the correct IP address and can be accessed via port 9151 from an outside
       connection eg. cell phone, other computer etc. by navigating to: ``https://<node_ip>:9151/status``

    #. Ensure that your worker is bonded with your staker - ``nucypher stake list`` and check that
       Worker is set correctly i.e. not ``0x0000``.

    #. Ensure that your node is listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few mins).

       If your node is on the status monitor page but:

        a. Does not have a green dot, you should ensure that your Ursula node can confirm activity (hint: does your worker address have ETH to pay gas?).
           Try locally running ``nucypher ursula confirm-activity``

        b. Has a *Last Seen* value of ``No Connection to Node`` then there may be connectivity issues with your
           node - redo the check in step #2.


What's the best way to run Ursula in the background?
----------------------------------------------------

Either through `Docker <https://docs.nucypher.com/en/latest/guides/ursula_configuration_guide.html#running-an-ursula-with-docker>`_
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
    >    --staking-address <your_staker_address>``

It takes two periods to observe rewards - if you deposit in period 0 and start a worker in the same period
(which calls ``confirmActivity()`` to receive work for the next period (1)), then in period 1 the Ursula
node does work and will get rewarded in period 2 for the work performed in period 1.

.. note::

    `Restaking <https://docs.nucypher.com/en/latest/architecture/sub_stakes.html#re-staking>`_ is enabled by
    default, and so NU inflation rewards are automatically restaked for you, and will be reflected in
    the ``Staked`` value of the above command.


How can I observe the settings (re-staking, winding down) for my stake?
-----------------------------------------------------------------------

Run::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>``


Can I extend the duration of my existing stake?
--------------------------------------------------------------

Yes, via the `prolong <https://docs.nucypher.com/en/latest/guides/staking_guide.html#prolong>`_ command.


Why is the duration/enactment of my stake longer than the value I used during setup?
------------------------------------------------------------------------------------

It is probably because `winding down <http://docs.nucypher.com/en/latest/architecture/sub_stakes.html#winding-down>`_
is disabled (default). If "winding down" is disabled, then the staking duration (``end period - current period``)
remains the same over time.

You can confirm that ``winding down`` is disabled by running::

    nucypher status stakers
    >    --provider <your_geth_provider>
    >    --network cassandra
    >    --staking-address <your_staker_address>``



How can I reuse an Ursula that was connected to the previous version of the testnet?
------------------------------------------------------------------------------------

#. Run ``nucypher ursula destroy`` to destroy the current configuration.
#. Repeat all of the steps with the new tokens in the `Staking Guide <https://docs.nucypher.com/en/latest/guides/staking_guide.html>`_.
#. Run ``nucypher ursula init`` per the `Ursula Configuration Guide <https://docs.nucypher.com/en/latest/guides/ursula_configuration_guide.html>`_.


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

We highly recommend delegating to a staking company rather than doing it yourself, if
you are not super familiar with running nodes for other networks.
