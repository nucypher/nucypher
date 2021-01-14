.. _ursula-config-guide:

================
Running a Worker
================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Workers.


Worker Requirements
-------------------

In order to be a successful Ursula operator, you will need a machine (physical or virtual) which is kept
online. As a frame of reference, maintaining an Ursula is similar to the deployment and maintenance of a
high-availability web service, with the addition of Ethereum accounts management. The worker must be tolerant
of internet connectivity problems, and power outages via a redundant power supply. However, short temporary
service disruptions such as upgrades are understandable.

Aside from the :ref:`base requirements <base-requirements>` for installation of the ``nucypher`` library:

* Dedicated physical/virtual machine
* Physical or SSH access
* 2GB RAM (minimum)
* x86 architecture
* 20GB HDD free storage - backups are required since data loss results in a malfunctioning worker
* Publicly available IP address - static where possible, NAT management where applicable
* TCP Port 9151 opened for network communication - firewall rules where applicable
* Access to a fully synced Ethereum provider e.g. local node, Infura, Alchemy etc.

..
    TODO: separate section on backups and data (#2285)

Workers can be run on cloud infrastructure – for example,
`Digital Ocean 4GB Basic Droplet <https://www.digitalocean.com/pricing/>`_ satisfies the memory and processing
power requirements listed above.

.. note::

    Additional requirements are needed to run local Ethereum node on the same system
    `additional requirements <https://docs.ethhub.io/using-ethereum/running-an-ethereum-node/>`_ are needed.


Configure and Run a Worker
--------------------------

This guide assumes that you already have ``nucypher`` installed, have initiated a stake, and bonded a worker.

Working Procedure:

.. References are needed for links because of the numbers in the section names

1) Ensure that a `Stake` is available (see :ref:`staking-guide`)
2) Run an ethereum node on the Worker's machine eg. geth, parity, etc. (see :ref:`Running an Ethereum node for Ursula <running-worker-eth-node>`)
3) Install ``nucypher`` on Worker node (see :doc:`/installation`)
4) Create and fund worker's ethereum address (see :ref:`Fund Worker Account with ETH <fund-worker-account>`)
5) Bond the Worker to a Staker (see :ref:`bond-worker`)
6) Configure and run a Worker node (see :ref:`Configure and Run Ursula <configure-run-ursula>`)
7) Ensure TCP port 9151 is externally accessible
8) Keep Worker node online!


.. _running-worker-eth-node:

1. Run an Ethereum node for Worker
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Worker Ursula transactions can be broadcasted using either a local or remote ethereum node.

For general background information about choosing a node technology and operation,
see https://web3py.readthedocs.io/en/stable/node.html.

.. _fund-worker-account:

2. Fund Worker Account with ETH
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Ensure that the worker's ethereum account has sufficient ETH to pay the gas for regular transactions, or
it may forgo subsidies (inflationary rewards).

**Reducing the gas costs burdened upon stakers/workers is an active and high-priority area of network development.**

.. note::

    For testnet, the worker account can be funded with Rinkeby testnet ETH via https://faucet.rinkeby.io/.


3. Ensure Worker account is bonded to Staker
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Ensure that the worker's ethereum account is bonded to the Staker. See :ref:`bond-worker`.


.. _configure-run-ursula:

4. Run Worker
^^^^^^^^^^^^^

Run Ursula via CLI (Interactive)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --network <NETWORK_NAME>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/<username>/.ethereum/geth.ipc`` - IPC Socket-based JSON-RPC server
    - ``https://<host>`` - HTTP(S)-based JSON-RPC server
    - ``wss://<host>:8080`` - Websocket(Secure)-based JSON-RPC server

``<NETWORK_NAME>`` is the name of the NuCypher network domain where the node will run.

.. note:: If you are using NuCypher's testnet, this name is ``ibex``.

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

Run Ursula with Docker
~~~~~~~~~~~~~~~~~~~~~~

Assuming geth is running locally, configure and run an Ursula using port and volume bindings:

.. code:: bash

    export NUCYPHER_KEYRING_PASSWORD=<YOUR KEYRING_PASSWORD>
    export NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ETH ACCOUNT PASSWORD>

    # Interactive Ursula-Worker Initialization
    docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD nucypher/nucypher:latest nucypher ursula init --provider file:///root/.ethereum/geth.ipc --network <NETWORK_NAME>

    # Daemonized Ursula
    docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run


Run Ursula with systemd
~~~~~~~~~~~~~~~~~~~~~~~~

#. Use this template to create a file named ``ursula.service`` and place it in ``/etc/systemd/system/``.

   .. code-block::

       [Unit]
       Description="Run 'Ursula', a NuCypher Staking Node."

       [Service]
       User=<YOUR USER>
       Type=simple
       Environment="NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ADDRESS PASSWORD>"
       Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
       ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run

       [Install]
       WantedBy=multi-user.target


#. Replace the following values with your own:

   * ``<YOUR USER>`` - The host system's username to run the process with
   * ``<YOUR WORKER ADDRESS PASSWORD>`` - Worker's ETH account password
   * ``<YOUR PASSWORD>`` - Ursula's keyring password
   * ``<VIRTUALENV PATH>`` - The absolute path to the python virtual environment containing the ``nucypher`` executable


#. Enable Ursula System Service

   .. code-block::

       $ sudo systemctl enable ursula


#. Run Ursula System Service

   To start Ursula services using systemd

   .. code-block::

       $ sudo systemctl start ursula


#. Check Ursula service status

   .. code-block::

       $ sudo systemctl status ursula

#. To restart your node service

   .. code-block:: bash

       $ sudo systemctl restart ursula

5. Monitor Worker
^^^^^^^^^^^^^^^^^

Ursula's Logs
~~~~~~~~~~~~~~

A reliable way to check the status of a worker node is to view the logs.  As a shortcut, nucypher's
logs can be viewed from the command line using ``tail``: `tail -f $(nucypher --logging-path)/nucypher.log`

Status Page
~~~~~~~~~~~
Once Ursula is running, you can view its public status page at ``https://<node_ip>:9151/status``.
It should eventually be listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).

Prometheus Endpoint
~~~~~~~~~~~~~~~~~~~
Ursula can optionally provide a `Prometheus <https://prometheus.io>`_ metrics endpoint to be used for as a data source
for real-time monitoring. The Prometheus client library is **not** installed by default and must be explicitly installed:

.. code:: bash

     (nucypher)$ pip install nucypher[ursula]

The metrics endpoint is disabled by default but can be enabled by providing the following
parameters to the ``nucypher ursula run`` command:

* ``--prometheus`` - a boolean flag to enable the prometheus endpoint
* ``--metrics-port <PORT>`` - the HTTP port to run the prometheus endpoint on

The corresponding endpoint, ``http://<node_ip>:<METRICS PORT>/metrics``, can be used as a Prometheus data source for
monitoring including the creation of alert criteria.

By default metrics will be collected every 90 seconds but this can be modified using the ``--metrics-interval`` option.
Collection of metrics will increase the number of RPC requests made to your web3 endpoint; increasing the frequency
of metrics collection will further increase this number.

During the Technical Contributor Phase of our testnet, *P2P Validator*
contributed a `self-hosted node monitoring suite <https://economy.p2p.org/nucypher-worker-node-monitoring-suite/amp/>`_
that uses a Grafana dashboard to visualize and monitor the metrics produced by the prometheus endpoint.

.. image:: ../.static/img/p2p_validator_dashboard.png
    :target: ../.static/img/p2p_validator_dashboard.png

.. note::

    Both the Ursula Status Page and Prometheus Endpoint are areas of active development.
