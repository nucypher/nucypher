.. _ursula-config-guide:

===================================
Worker (Ursula) Configuration Guide
===================================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Workers.

Worker Overview
----------------

*Worker* - (aka "Ursula") Active network participant who carries out re-encryption work orders.

The Worker is the bonded delegate of a Staker and an active network node. Workers must remain online to provide
uninterrupted re-encryption services on-demand. Each staking account or Staker is bonded to exactly one Worker.
The worker's ethereum account must remain unlocked to send automated work confirmation transactions and have enough
ether to pay for transaction gas; however, it is *not* necessary (and potentially risky) to hold NU tokens on a worker's
account for any reason.

Working Procedure:

.. References are needed for links because of the numbers in the section names

1) Ensure that a `Stake` is available (see :ref:`staking-guide`)
2) Run an ethereum node on the Worker's machine eg. geth, parity, etc. (see :ref:`Running an Ethereum node for Ursula <running-worker-eth-node>`)
3) Install ``nucypher`` on Worker node (see :doc:`/guides/installation_guide`)
4) Create and fund worker's ethereum address (see :ref:`Fund Worker Account with ETH <fund-worker-account>`)
5) Bond the Worker to a Staker (see :ref:`bond-worker`)
6) Configure and run a Worker node (see :ref:`Configure and Run Ursula <configure-run-ursula>`)
7) Ensure TCP port 9151 is externally accessible (see `Ursula / Worker Requirements`_)
8) Keep Worker node online!


.. _running-worker-eth-node:

1. Running an Ethereum node for Ursula
----------------------------------------

Worker (Ursula) transactions can be broadcasted using either a local or remote ethereum node. See :ref:`using-eth-node`
for more information.


.. _fund-worker-account:

2. Fund Worker Account with ETH
-------------------------------
Ensure that the worker's ethereum account has ETH for transaction gas.

.. note::

    For Testnet, this account can be funded with Görli testnet ETH via https://goerli-faucet.slock.it/.


3. Ensure Worker account is bonded to Staker
--------------------------------------------
Ensure that the worker's ethereum account is bonded to the Staker. See :ref:`bond-worker`.


.. _configure-run-ursula:

4. Configure and Run Ursula
---------------------------

Ursula / Worker Requirements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A fully synced ethereum node or "provider" is required for the worker to read and write to nucypher's smart contracts.

In order to be a successful Ursula operator, you will need a machine (physical or virtual) which
can be kept online consistently without interruption and is externally accessible via TCP port 9151.
The well-behaved worker will accept work orders for re-encryption at-will, and be rewarded as a result.

It is assumed that you already have nucypher installed, have initiated a stake, and bonded a worker.

The installation procedure for the Ursula (Worker) node is exactly the same as for Staker.
See the  `Installation Guide`_ and `Staking_Guide`_ for more details.

.. _Installation Guide: installation_guide.html
.. _Staking_Guide: staking_guide.html


Running an Ursula via CLI (Interactive)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --network <NETWORK_NAME>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/<username>/.ethereum/geth.ipc`` - IPC Socket-based JSON-RPC server
    - ``https://<host>`` - HTTP(S)-based JSON-RPC server
    - ``wss://<host>:8080`` - Websocket(Secure)-based JSON-RPC server

``<NETWORK_NAME>`` is the name of the NuCypher network domain where the node will run.

.. note:: If you are using NuCypher's testnet, this name is ``gemini``.

Create a password when prompted

.. code:: bash

    Enter a password to encrypt your keyring: <YOUR PASSWORD HERE>


.. important::::
    Save your password as you will need it to relaunch the node, and please note:

    - Minimum password length is 16 characters
    - Do not use a password that you use anywhere else

Run the Ursula!

.. code:: bash

    (nucypher)$ nucypher ursula run --interactive


Verify Ursula Blockchain Connection (Interactive)

This will drop your terminal session into the “Ursula Interactive Console” indicated by the ``>>>``.
Verify that the node setup was successful by running the ``status`` command.

.. code:: bash

    Ursula >>> status


To view a list of known Ursulas, execute the ``known_nodes`` command

.. code:: bash

    Ursula >>> known_nodes


You can also view your node’s network status webpage by navigating your web browser to ``https://<your-node-ip-address>:9151/status``.
Ensure that this URL can be accessed publicly: it means that your node can be seen by other NuCypher nodes.

.. NOTE::
    Since Ursulas self-sign TLS certificates, you may receive a warning from your web browser.


To stop your node from the interactive console and return to the terminal session:

.. code:: bash

    Ursula >>> stop


.. _run-ursula-with-docker:

Running an Ursula with Docker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assuming geth is running locally, configure and run an Ursula using port and volume bindings:

.. code:: bash

    export NUCYPHER_KEYRING_PASSWORD=<YOUR KEYRING_PASSWORD>
    export NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ETH ACCOUNT PASSWORD>

    # Interactive Ursula-Worker Initialization
    docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD nucypher/nucypher:latest nucypher ursula init --provider file:///root/.ethereum/geth.ipc --network <NETWORK_NAME>

    # Daemonized Ursula
    docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run

``<YOUR STAKING ADDRESS>`` is the address you've staked from when following the :ref:`staking-guide`.


5. Monitoring Ursula
--------------------

Status Page
~~~~~~~~~~~
Once Ursula is running, you can view its public status page at ``https://<node_ip>:9151/status``.
It should eventually be listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).

Prometheus Endpoint
~~~~~~~~~~~~~~~~~~~
Ursula can optionally provide a `Prometheus <https://prometheus.io>`_ metrics endpoint to be used for as a data source
for real-time monitoring. This functionality is disabled by default but can be enabled by providing the following
parameters to the ``nucypher ursula run`` command:

* ``--prometheus`` - a boolean flag to enable the prometheus endpoint
* ``--metrics-port <PORT>`` - the HTTP port to run the prometheus endpoint on

The corresponding endpoint, ``http://<node_ip>:<METRICS PORT>/metrics``, can be used as a Prometheus data source for
monitoring including the creation of alert criteria.

Prometheus is **not** installed by default and must be explicitly installed:

.. code:: bash

     (nucypher)$ pip install nucypher[ursula]


.. note::

    Both the Ursula Status Page and Prometheus Endpoint are areas of active development.
