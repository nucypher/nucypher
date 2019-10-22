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

First, you install geth. You'll need to run it in the background and sync up.
For testnet, it is:

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

With Docker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Recall the volume mounts: `-v <path to a directory on your computer>:/root/.local/share/` which is where your Nucypher node stores persistent data as well as accesses ipc with your locally running geth node.

Execute the following commands (Ubuntu):

.. code:: bash

    export NUCYPHER_KEYRING_PASSWORD=<your keyring password>
    export MY_IP=$(wget -q -O - ifconfig.me);
    export NUCYPHER_WORKER_ADDRESS=<eth account checksum of your worker>
    export NUCYPHER_STAKER_ADDRESS=<eth account checksum of your staker>
    export NUCYPHER_WORKER_ETH_PASSWORD=<your eth account password>

    # init your worker
    docker run -v /home/ubuntu:/root/.local/share/ -e NUCYPHER_KEYRING_PASSWORD -it nucypher/nucypher:latest nucypher ursula init --provider /root/.local/share/geth/.ethereum/goerli/geth.ipc --poa --worker-address $NUCYPHER_WORKER_ADDRESS --staker-address $NUCYPHER_STAKER_ADDRESS --rest-host $MY_IP

    # and then run the worker in the background
    docker run -v /home/ubuntu:/root/.local/share/ -dit --restart unless-stopped -p 9151:9151  -e NUCYPHER_KEYRING_PASSWORD -e NUCYPHER_WORKER_ETH_PASSWORD  nucypher/nucypher:latest nucypher ursula run --teacher discover.nucypher.network:9151 --poa


Without Docker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --poa --staker-address <YOUR STAKER ADDRESS>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/ubuntu/.ethereum/goerli/geth.ipc`` - Geth Node on Görli testnet running under user ``ubuntu`` (most probably that's what you need).
    - ``ipc:///tmp/geth.ipc``   - Geth Development Node
    - ``http://localhost:7545`` - Ganache TestRPC (HTTP-JSON-RPC)
    - ``ws://0.0.0.0:8080``     - Websocket Provider

``<YOUR STAKER ADDRESS>`` is the address you've staked from when following the
 :ref:`staking-guide`.


3. Enter or confirm your public-facing IPv4 address when prompted
-------------------------------------------------------------------

.. code:: bash

    Enter Nodes Public IPv4 Address: <YOUR NODE IP HERE>

Additionally, make sure that your port 9151 is open.


4. Create a password when prompted
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

    (nucypher)$ nucypher ursula run --poa
