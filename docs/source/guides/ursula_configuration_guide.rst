.. _ursula-config-guide:

==========================
Ursula Configuration Guide
==========================

1. Install NuCypher and geth
------------------------------

If you want to run a NuCypher node which participates in decentralized network,
you need to install it first. The installation procedure for the Ursula (Worker)
node is exactly the same as for Staker.

First, you install geth. You'll need to run it in the background and sync up.
For testnet, it is:

.. code:: bash

    $ geth --goerli

You need to create a software-controlled account in geth:

.. code:: bash

    $ geth attach ~/.ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts[0]
    ["0xc080708026a3a280894365efd51bb64521c45147"]

So, your worker account is ``0xc080708026a3a280894365efd51bb64521c45147`` in
this case.

Install ``nucypher`` either by doing ``sudo pip3 install nucypher`` if you have
a dedicated instance or container, or with a ``virtualenv``:

.. code:: bash

    $ virtualenv -p python3 nucypher
    $ source nucypher/bin/activate
    (nu)$ pip3 install nucypher

Before continuing, Verify your ``nucypher`` installation and entry points are functional:

Activate your virtual environment (if you already didn't) and run the ``nucypher --help`` command

.. code:: bash

    $ source nucypher/bin/activate
    ...
    (nucypher)$ nucypher --help


You will see a list of possible usage options (``--version``, ``-v``, ``--dev``, etc.) and commands (``status``, ``ursula``).
For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.

If your installation in non-functional, be sure you have the latest version installed, and see the `Installation Guide`_

.. _Installation Guide: installation_guide.html



2. Configure a new Ursula node
--------------------------------

*Decentralized Ursula Configuration*

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --network <NETWORK NAME> --poa


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``file:///tmp/geth.ipc``   - Geth Development Node
    - ``http://localhost:7545`` - Ganache TestRPC (HTTP-JSON-RPC)
    - ``ws://0.0.0.0:8080``     - Websocket Provider


3. Enter or confirm your public-facing IPv4 address when prompted
-------------------------------------------------------------------

.. code:: bash

    Enter Nodes Public IPv4 Address: <YOUR NODE IP HERE>


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

    (nucypher)$ nucypher ursula run --teacher <SEEDNODE_URI> --interactive


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
