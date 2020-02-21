.. _ursula-config-guide:

===================================
Worker (Ursula) Configuration Guide
===================================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Workers.

Worker Overview
----------------

*Worker* - (aka "Ursula") Active network participant, Carries out re-encryption work orders.

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

Run Geth with Docker
~~~~~~~~~~~~~~~~~~~~~

Run a local geth node on Görli using volume bindings:

.. code:: bash

    docker run -it -p 30303:30303 -v ~/.ethereum:/root/.ethereum ethereum/client-go --goerli

For alternate geth configuration via docker see:
`Geth Docker Documentation <https://geth.ethereum.org/docs/install-and-build/installing-geth#run-inside-docker-container>`_.


Run Geth with the CLI
~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    $ geth --goerli --nousb
    ... (geth log output)

Create a software-controlled account in geth in another console:

.. code:: bash

    $ geth attach ~/.ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts[0]
    ["0xc080708026a3a280894365efd51bb64521c45147"]

The new account is ``0xc080708026a3a280894365efd51bb64521c45147`` in this case.


.. _fund-worker-account:

2. Fund Worker Account with ETH
-------------------------------
Ensure that the worker's ethereum account has ETH for transaction gas.

During testnet, this account can be funded with Görli testnet ETH via https://goerli-faucet.slock.it/.


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

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --poa --staker-address <YOUR STAKER ADDRESS> --network <NETWORK_NAME>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/ubuntu/.ethereum/goerli/geth.ipc`` - Geth Node on Görli testnet running with user ``ubuntu`` (default)
    - ``ipc:///tmp/geth.ipc``   - Geth Development Node
    - ``http://localhost:8545`` - Geth/Parity RPC-HTTP
    - ``ws://0.0.0.0:8080``     - Websocket Provider

``<YOUR STAKER ADDRESS>`` is the address you've staked from when following the :ref:`staking-guide`.

``<NETWORK_NAME>`` is the name of the NuCypher network domain where the node will run.

.. note:: If you're participating in NuCypher's incentivized testnet, this name is ``cassandra``.


.. note:: If you're a preallocation user, recall that you're using a contract to stake.
  Replace ``<YOUR STAKER ADDRESS>`` with the contract address.
  If you don't know this address, you'll find it in the preallocation file.

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

Assuming geth is running locally on goerli, configure and run an Ursula using port and volume bindings:

.. code:: bash

    export NUCYPHER_KEYRING_PASSWORD=<YOUR KEYRING_PASSWORD>
    export NUCYPHER_WORKER_ETH_PASSWORD=<YOUR WORKER ETH ACCOUNT PASSWORD>

    # Interactive Ursula-Worker Initialization
    docker run -it -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD nucypher/nucypher:latest nucypher ursula init --provider file:///root/.ethereum/goerli/geth.ipc --staker-address <YOUR STAKING ADDRESS> --network <NETWORK_NAME>

    # Daemonized Ursula
    docker run -d -v ~/.local/share/nucypher:/root/.local/share/nucypher -v ~/.ethereum/:/root/.ethereum -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run

``<YOUR STAKING ADDRESS>`` is the address you've staked from when following the :ref:`staking-guide`.
