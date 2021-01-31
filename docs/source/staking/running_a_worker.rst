.. _ursula-config-guide:

================
Running a Worker
================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Workers.

Overview
----------

Worker's role in the network
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Worker nodes perform periodic automated transactions to signal continued commitment to providing service.
The worker's ethereum account must remain unlocked while the node is running. Worker ethereum accounts do not need NU
and only need enough ETH to pay for gas fees.  The average cost of a commitment is ~200k gas.


Workers nodes have three core components
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* Ethereum software wallet (keystore)
* Local or hosted ethereum provider
* Worker node; Local or cloud server


Minimum system requirements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* 20GB storage
* 2GB RAM
* x86 architecture
* Static IP address
* Exposed TCP port 9151

Workers can be run on cloud infrastructure – for example,
`Digital Ocean 4GB Basic Droplet <https://www.digitalocean.com/pricing/>`_ satisfies requirements listed above.


Best Practices
^^^^^^^^^^^^^^

**Three core areas of responsibility**

#. Keystore Diligence
#. Datastore Diligence
#. Network Participation

Here are some best practices:

- Backup and secure the worker's private keys (ethereum and nucypher keystores).
- Maintain a regular backup of the worker's database.
- Maintain high uptime; Keep downtime brief when required by updates or reconfiguration.
- Update when a new version is available.

..
    TODO: separate section on backups and data (#2285)

1. Establish Ethereum Provider
-------------------------------

Worker Ursula transactions can be broadcasted using either a local or remote ethereum node.

For general background information about choosing a node technology and operation,
see https://web3py.readthedocs.io/en/stable/node.html.

.. note::

    Additional requirements are needed to run a local Ethereum node on the same system
    `additional requirements <https://docs.ethhub.io/using-ethereum/running-an-ethereum-node/>`_ are needed.


2. Establish Worker Ethereum Account
-------------------------------------

By default, all transaction and message signing requests are forwarded to the configured ethereum provider.
To use another ethereum provider (e.g. Infura, Alchemy, Another Hosted/Remote Node) a local transaction signer must
be configured in addition to the broadcasting node.  For workers this can be a software wallet, or clef.
For more detailed information see :doc:`/references/signers`

Because worker nodes perform periodic automated transactions to signal continued commitment to providing service,
The worker's ethereum account must remain unlocked while the node is running. While there are several types of accounts
workers can use, a software based wallet is easiest method.

To create a new ethereum software account using the geth CLI run follow the instructions:

.. code:: bash

    geth account new
    ...

.. important::

    - Do not keep NU on the worker account: Workers **do not** need NU for any reason.
    - Only keep enough ETH to pay for gas fees (The average cost of a commitment is ~200k gas).
    - Store the ethereum account password in a password manager
    - Backup the worker's private keys

.. important::  If the worker's ethereum private key is lost or compromised

    #. Create a new ethereum keypiar
    #. Reconfigure the worker to use the new account ``nucypher ursula config --worker-address <ADDRESS>``
    #. Bond the new address from the staking account (or inform the staking party).

    Note that stakers can only be rebond once every two periods.


3. Run Worker
-------------

.. _run-ursula-with-docker:


Run Worker with Docker (Recommended)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Setup Docker
~~~~~~~~~~~~~

#. Install `Docker <https://docs.docker.com/install/>`_
#. (Optional) Follow these post install instructions: `https://docs.docker.com/install/linux/linux-postinstall/ <https://docs.docker.com/install/linux/linux-postinstall/>`_
#. Get the latest nucypher image:

.. code:: bash

    docker pull nucypher/nucypher:latest


Export worker environment variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    # Passwords are used for both creation and unlocking
    export NUCYPHER_KEYRING_PASSWORD=<YOUR KEYRING_PASSWORD>
    export NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ETH ACCOUNT PASSWORD>

Initialize a new Worker
~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    docker run -it --rm \
    --name ursula       \
    -v ~/.local/share/nucypher:/root/.local/share/nucypher \
    -v ~/.ethereum/:/root/.ethereum \
    -p 9151:9151                    \
    -e NUCYPHER_KEYRING_PASSWORD    \
    nucypher/nucypher:latest        \
    nucypher ursula init            \
    --provider <PROVIDER URI>       \
    --network <NETWORK NAME>        \
    --signer <SIGNER URI>


Replace the following values with your own:

   * ``<PROVIDER URI>`` - The URI of a local or hosted ethereum node
   * ``<NETWORK NAME>`` - The name of a nucypher network (mainnet, ibex, or lynx)
   * ``<SIGNER URI>`` - The URI to an ethereum keystore or signer: `keystore:///root/.ethereum/keystore`


Launch the worker
~~~~~~~~~~~~~~~~~

.. code:: bash

    docker run -d --rm \
    --name ursula      \
    -v ~/.local/share/nucypher:/root/.local/share/nucypher \
    -v ~/.ethereum/:/root/.ethereum  \
    -p 9151:9151                     \
    -e NUCYPHER_KEYRING_PASSWORD     \
    -e NUCYPHER_WORKER_ETH_PASSWORD  \
    nucypher/nucypher:latest         \
    nucypher ursula run              \
    --network <NETWORK NAME>

Replace the following values with your own:

   * ``<NETWORK NAME>`` - The name of a nucypher network (mainnet, ibex, or lynx)

View worker logs
~~~~~~~~~~~~~~~~

.. code:: bash

    docker logs -f ursula

Upgrading to a newer version
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When a new version is available a docker-launched worker can be updated by stopping the worker,
running docker pull, then start the worker.

.. code:: bash

    docker stop ursula
    docker pull nucypher/nucypher:latest
    docker run ...


Run Worker with systemd (Alternate)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Instead of using docker, the nucypher worker can be run as a systemd service.

#. Install nucypher into a virtual environment.

    .. code-block::

        $(nucypher) pip install -U nucypher


#. Configure the worker using the nucypher CLI.

    .. code-block::

        $(nucypher) nucypher ursula init --provider <PROVIDER URI> --network <NETWORK NAME> --signer <SIGNER URI>


#. Use this template to create a file named ``ursula.service`` and place it in ``/etc/systemd/system/``.

.. code-block::

   [Unit]
   Description="Ursula, a NuCypher Worker."

   [Service]
   User=<YOUR USER>
   Type=simple
   Environment="NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ADDRESS PASSWORD>"
   Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
   ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run

   [Install]
   WantedBy=multi-user.target


Replace the following values with your own:

   * ``<YOUR USER>`` - The host system's username to run the process with (best practice is to use a dedicated user)
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

    # Application Logs
    $ tail -f ~/.local/share/nucypher/nucypher.log

    # Systemd status
    $ systemctl status ursula

    # Systemd Logs
    $ journalctl -f -t ursula


#. To restart your node service

.. code-block:: bash

   $ sudo systemctl restart ursula

4. Qualify Worker
^^^^^^^^^^^^^^^^^

Workers must be fully qualified (funded and bonded) in order to fully start.  Workers
that are launched before qualification will pause until they are have a balance greater than 0 ETH,
and are bonded to a staking account.  Once both of these requirements are met, thw worker will automatically
resume startup.

Waiting for qualification:

.. code-block:: bash

    ...
    Authenticating Ursula
    Qualifying worker
    ⓘ  Worker startup is paused. Waiting for bonding and funding ...
    ⓘ  Worker startup is paused. Waiting for bonding and funding ...
    ⓘ  Worker startup is paused. Waiting for bonding and funding ...

Resuming startup after funding and bonding:

.. code-block:: bash

    ...
    ⓘ  Worker startup is paused. Waiting for bonding and funding ...
    ✓ Worker is bonded to 0x37f320567b6C4dF121302EaED8A9B7029Fe09Deb
    ✓ Worker is funded with 0.01 ETH
    ✓ External IP matches configuration
    Starting services
    ✓ Database Pruning
    ✓ Work Tracking
    ✓ Rest Server https://1.2.3.4:9151
    Working ~ Keep Ursula Online!

.. _fund-worker-account:


5. Monitor Worker
------------------

Ursula's Logs
^^^^^^^^^^^^^

A reliable way to check the status of a worker node is to view the logs.

View logs for a docker-launched Ursula:

.. code:: bash

    docker logs -f ursula

View logs for a CLI-launched or systemd Ursula:

.. code:: bash

    # Application Logs
    tail -f ~/.local/share/nucypher/nucypher.log

    # Systemd Logs
    journalctl -f -t ursula


Status Webpage
^^^^^^^^^^^^^^

Once Ursula is running, you can view its public status page at ``https://<node_ip>:9151/status``.
It should eventually be listed on the `Status Monitor Page <https://status.nucypher.network>`_ (this can take a few minutes).


Prometheus Endpoint
^^^^^^^^^^^^^^^^^^^

Ursula can optionally provide a `Prometheus <https://prometheus.io>`_ metrics endpoint to be used for as a data source
for real-time monitoring.  For docker users, the Prometheus client library is installed by default.

For pip installations, The Prometheus client library is **not** included by default and must be explicitly installed:

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
