.. _ursula-config-guide:

================
Running a Worker
================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Workers.

Overview
----------

Workers' role in the network
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Worker is the bonded delegate of a Staker and an active network node.  Each staking account
or "Staker" is bonded to exactly one Worker. Workers must remain online to provide uninterrupted
re-encryption services to network users on-demand and perform periodic automated transactions to
signal continued commitment to availability.


Worker nodes have three core components
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

**The state of worker diligence**

Workers can demonstrate a vested interest in the success of the network by adhering to
three core areas of responsibility (in order of importance):

**#1 Keystore Diligence**

Requires that the custodian keep track of a secret seed which can be used to generate the entire keystore.

- Keep an offline backup up mnemonic seed phrases.
- Use a password manager to generate a strong password when one is required.

**#2 Datastore Diligence**

Requires that material observed during the runtime be stored.

A running worker stores peer metadata, re-encryption key fragments ("Kfrags"), and "treasure maps".

Loss of stored re-encryption key fragments will indicate slashing on the bonded stake.
If a worker node has already agreed to enforce a policy, then loses a Kfrag, network users
can issue a challenge which is verified onchain by the Adjudicator contract.

As a civic matter, datastore diligence is important for Ursula for several reasons
Including storing node validity status (and thus refraining from pestering nodes
with unnecessary additional verification requests). Loss of peer metadata means that the worker
must rediscover and validate peers, slowly rebuilding it's network view while contributing to
lessened availability and higher network traffic.

- Maintain regular backups of the worker's filesystem and database.


**#3 Runtime Diligence**

Requires active and security-conscious participation in the network.

A bonded node that is unreachable or otherwise invalid will be unable to accept new
policies, and miss out on inflation rewards.  The bonded stake will remain locked until
the entre commitment is completed.

- Secure the worker's keystore used in deployment.
- Keep enough ETH on the worker to pay for gas.
- Maintain high uptime; Keep downtime brief when required by updates or reconfiguration.
- Update when a new version is available.
- Monitor a running ursula for nominal behaviour and period confirmations.

.. caution::
    The worker's ethereum account must have enough ether to pay for transaction gas;
    however, it is *not* necessary (and potentially risky) to hold NU tokens on a worker's
    account for any reason.

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
For more detailed information see :doc:`/references/signers`.

Because worker nodes perform periodic automated transactions to signal continued commitment to providing service,
The worker's ethereum account must remain unlocked while the node is running. While there are several types of accounts
workers can use, a software based wallet is the easiest method.

.. note::

    To create a new ethereum software account using the ``geth`` CLI:

    .. code:: bash

        geth account new
        ...

.. caution::

    Stay safe handling ETH and NU:

    - Workers **do not** need NU for any reason: Do not keep NU on the worker's account.
    - Do not store ETH on the worker - Keep only enough to pay for gas fees.
    - Store the ethereum account password in a password manager when using a keystore.

.. important::

    If the worker's ethereum private key is lost or compromised:

    #. Inform the Staking operator/party.
    #. Create a new ethereum account
    #. Reconfigure the worker to use the new account ``nucypher ursula config --worker-address <ADDRESS> --signer <SIGNER URI>``
    #. Bond the new address from the staking account (or inform the staking party).

    Note that stakers can only rebond to a new worker once every two periods.


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

When a new version is available a docker-launched worker can be updated by
stopping the worker, running docker pull, then restarting the worker.

.. code:: bash

    docker stop ursula
    docker pull nucypher/nucypher:latest
    docker run ...


Run Worker with systemd (Alternate)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Instead of using docker, the nucypher worker can be run as a systemd service.

.. note::

    Running a worker with systemd required a local installation of nucypher.
    See :doc:`/references/pip-installation`

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


Run Worker Manually
^^^^^^^^^^^^^^^^^^^

If you'd like to use another own method of running the worker process in the background, or are
using one of the testnets, here is how to run Ursula using the CLI directly.

.. code

    # Initialize Ursula
    nucypher ursula init --provider <PROVIDER URI> --network <NETWORK NAME> --signer <SIGNER URI>

    # Run Worker
    nucypher ursula run


Replace the following values with your own:

   * ``<PROVIDER URI>`` - The URI of a local or hosted ethereum node
   * ``<NETWORK NAME>`` - The name of a nucypher network (mainnet, ibex, or lynx)
   * ``<SIGNER URI>`` - The URI to an ethereum keystore or signer: `keystore:///root/.ethereum/keystore`


4. Qualify Worker
-----------------

Workers must be fully qualified (funded and bonded) in order to fully start.  Workers
that are launched before qualification will pause until they are have a balance greater than 0 ETH,
and are bonded to a staking account.  Once both of these requirements are met, the worker will automatically
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
