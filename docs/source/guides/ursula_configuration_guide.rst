.. _ursula-config-guide:

==========================
Ursula Configuration Guide
==========================

1. Install geth Ethereum node
------------------------------

If you want to run a NuCypher node that participates in the decentralized network,
you need to install it first. The installation procedure for the Ursula (Worker)
node is exactly the same as for Staker.

You will need a machine (could be a physical computer or a cloud instance) which
can be externally accessed via a TCP port 9151 (make sure it can be accessed
from the outside).

You'll need to install and run geth until synced.


Run geth Using Docker
~~~~~~~~~~~~~~~~~~~~~~~~

Run a local geth node on goerli using volume bindings:

.. code:: bash

    docker run -it -p 30303:30303 -v ~/.ethereum:/root/.ethereum ethereum/client-go --goerli

For alternate methods of running geth via docker see: `Geth Docker Documentation <https://geth.ethereum.org/docs/install-and-build/installing-geth#run-inside-docker-container>`_.


Run Geth via CLI
~~~~~~~~~~~~~~~~~

.. code:: bash

    $ geth --goerli --nousb

You need to create a software-controlled account in geth:

.. code:: bash

    $ geth attach ~/.ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts[0]
    ["0xc080708026a3a280894365efd51bb64521c45147"]

So, your worker account is ``0xc080708026a3a280894365efd51bb64521c45147`` in
this case.

Fund this account with Görli testnet ETH! To do it, go to
https://goerli-faucet.slock.it/.

2. Install NuCypher
--------------------------------

Install ``nucypher`` with ``docker`` (See :doc:`/guides/installation_guide`) or ``pip`` (below).

Standard Pip Install
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before installing ``nucypher``, you may need to install necessary developer
tools and headers, if you don't have them already. In Ubuntu, Debian, Linux Mint
or similar distros, that is:

.. code:: bash

    $ sudo apt install build-essential python3-dev python3-pip

Install ``nucypher`` either by doing ``sudo pip3 install nucypher`` if you have
a dedicated instance or container, or with a ``virtualenv``:

.. code:: bash

    $ virtualenv -p python3 nucypher
    $ source nucypher/bin/activate
    (nu)$ pip3 install nucypher

Before continuing, verify that your ``nucypher`` installation and entry points are functional:

Activate your virtual environment (if you haven't already) and run the ``nucypher --help`` command

.. code:: bash

    $ source nucypher/bin/activate
    ...
    (nucypher)$ nucypher --help


You will see a list of possible usage options (``--version``, ``-v``, ``--dev``, etc.) and commands (``status``, ``ursula``).
For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.

If your installation is non-functional, be sure you have the latest version installed, and see the `Installation Guide`_

.. _Installation Guide: installation_guide.html


3. Configure a new Ursula node
--------------------------------


Running an Ursula with Docker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assuming geth is running locally on goerli, configure and run an Ursula using port and volume bindings:

.. code:: bash

    export NUCYPHER_KEYRING_PASSWORD=<your keyring password>
    export NUCYPHER_WORKER_ETH_PASSWORD=<your eth account password>

    # Interactive Ursula-Worker Initialization
    docker run -it -v ~/.ethereum:/root/.ethereum -v ~/.local/share/nucypher:/root/.local/share/nucypher -e NUCYPHER_KEYRING_PASSWORD nucypher:latest nucypher ursula init --provider file:///root/.ethereum/goerli/geth.ipc --staker-address <YOUR STAKING ADDRESS>

    # Daemonized Ursula
    docker run -d -v ~/.ethereum:/root/.ethereum -v ~/.local/share/nucypher:/root/.local/share/nucypher -p 9151:9151 -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD nucypher/nucypher:latest nucypher ursula run --teacher discover.nucypher.network:9151 --provider file:///root/.ethereum/goerli/geth.ipc

``<YOUR STAKING ADDRESS>`` is the address you've staked from when following the :ref:`staking-guide`.

Running an Ursula via CLI
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --poa --staker-address <YOUR STAKER ADDRESS>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/ubuntu/.ethereum/goerli/geth.ipc`` - Geth Node on Görli testnet running under user ``ubuntu`` (most probably that's what you need).
    - ``ipc:///tmp/geth.ipc``   - Geth Development Node
    - ``http://localhost:7545`` - Ganache TestRPC (HTTP-JSON-RPC)
    - ``ws://0.0.0.0:8080``     - Websocket Provider

``<YOUR STAKER ADDRESS>`` is the address you've staked from when following the
 :ref:`staking-guide`.

.. note:: If you're a preallocation user, recall that you're using a contract to stake.
  Replace ``<YOUR STAKER ADDRESS>`` with the contract address.
  If you don't know this address, you'll find it in the preallocation file.


3. Create a password when prompted
-----------------------------------------

.. code:: bash

    Enter a password to encrypt your keyring: <YOUR PASSWORD HERE>


.. important::::
    Save your password as you will need it to relaunch the node, and please note:

    - Minimum password length is 16 characters
    - Do not use a password that you use anywhere else

5. Connect to a Fleet
------------------------

.. code:: bash

    (nucypher)$ nucypher ursula run --teacher discover.nucypher.network:9151 --interactive


6. Verify Ursula Blockchain Connection (Interactive)
------------------------------------------------------

This will drop your terminal session into the “Ursula Interactive Console” indicated by the ``>>>``.
Verify that the node setup was successful by running the ``status`` command.

.. code:: bash

    Ursula >>> status


7. To view a list of known Ursulas, execute the ``known_nodes`` command
-------------------------------------------------------------------------

.. code:: bash

    Ursula >>> known_nodes


You can also view your node’s network status webpage by navigating your web browser to ``https://<your-node-ip-address>:9151/status``.
It's a good idea to ensure that this URL can be accessed publicly: it means that
your node can be seen by other NuCypher nodes.

.. NOTE::
    Since Ursulas self-sign TLS certificates, you may receive a warning from your web browser.


8. To stop your node from the interactive console and return to the terminal session:
---------------------------------------------------------------------------------------

.. code:: bash

    Ursula >>> stop


9. Subsequent node restarts do not need the teacher endpoint specified:
-------------------------------------------------------------------------

.. code:: bash

    (nucypher)$ nucypher ursula run
