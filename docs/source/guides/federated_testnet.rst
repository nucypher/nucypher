..
   TODO: #1354 - Find a home for this guide

:orphan:

=============================================
NuCypher Federated Testnet (NuFT) Setup Guide
=============================================

This guide is for individuals who intend to spin-up and maintain an Ursula node in the early stages of the NuFT 
while working with the NuCypher team to improve user experience, comfort, and code-quality of the NuCypher network. 
Following the steps will launch a functioning federated-only Ursula node operating from a machine you control. 
Before getting started, please note: 

* We encourage you to launch your node on a machine that is able to remain online with as few interruptions as possible, for as long as possible. Although it is possible to restart a node, excessive deactivation/reactivation can contribute to a lack of usable feedback from the test network. Additionally, node uptime will be important for proper functioning of Mainnet. Thus, it’s worthwhile to start working with a reliable machine now so that your nodes are compliant with the network's uptime requirements when the time comes.

* Setup requires knowledge of your machine’s public-facing IPv4 address and local network configuration. It is advised to use a static IP address since changing IP addresses will require node reconfiguration. Configure port-forwarding rules on port 9151 if you are operating a node behind a firewall.  Once successfully up and running, your node will be discoverable by all other nodes in the test network.

* NuFT transmits application errors and crash reports to NuCypher’s sentry server.  This functionality is enabled by default for NuFT only and will be deactivated by default for mainnet.


.. warning::

  The “NuCypher Federated Testnet” (NuFT) is an experimental pre-release of nucypher.  Expect bugs, downtime, and unannounced domain-wide restarts. NuFT nodes do not connect to any blockchain. **DO NOT** perform transactions using NuFT node addresses.

.. important::

  Exiting the setup process prior to completion may lead to issues/bugs. If you encounter issues, report feedback by opening an Issue on our GitHub (https://github.com/nucypher/nucypher/issues)

Contents
--------

* `Stage A | Install The NuCypher Environment`_
* `Stage B | Configure Ursula`_
* `Stage C | Run the Node (Interactive Method)`_
* `Stage C | Run the Node (System Service Method)`_


Configure a NuFT Node
---------------------

Stage A | Install The NuCypher Environment
------------------------------------------

1. Install Python and Git
    
If you don’t already have them, install Python and git.
As of January 2019, we are working with Python 3.6, 3.7, and 3.8.

* Official Python Website: https://www.python.org/downloads/
* Git Install Guide: https://git-scm.com/book/en/v2/Getting-Started-Installing-Git


2.  Create Virtual Environment
    
Create a system directory for the nucypher application code:
    
.. code::

    $ mkdir nucypher


Create a virtual environment for your node to run in using ``virtualenv``:
    
.. code::

    $ virtualenv nucypher -p python3
    ...

Activate your virtual environment:
    
.. code::

    $ source nucypher/bin/activate
    ...
    (nucypher)$


3. Install NuCypher
    
Install ``nucypher`` with ``git`` and ``pip3`` into your virtual environment.

.. code::

    (nucypher)$ pip3 install nucypher

.. note::

   We recommend NuFT nodes install directly from main to help ensure your node is using pre-released features and hotfixes


Re-activate your environment after installing
    
.. code::

    $ source nucypher/bin/activate
    ...
    (nucypher)$ 


Stage B | Configure Ursula
--------------------------

1. Verify that the installation was successful
    
Activate your virtual environment and run the ``nucypher --help`` command
    
.. code::

    $ source nucypher/bin/activate
    ...
    (nucypher)$ nucypher --help

You will see a list of possible usage options (``--version``, ``-v``, ``--dev``, etc.) and commands (``status``, ``ursula``). For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.

2. Configure a new Ursula node
    
.. code::

    (nucypher)$ nucypher ursula init --federated-only
    ...

3. Enter your public-facing IPv4 address when prompted

.. code::

    Enter Node's Public IPv4 Address: <YOUR NODE IP HERE>

4. Enter a password when prompted

.. code::

    Enter a passphrase to encrypt your keyring: <YOUR PASSWORD HERE>


.. important::

    Save your password as you will need it to relaunch the node, and please note:

    - Minimum password length is 16 characters
    - There is no password recovery process for NuFT nodes
    - Do not use a password that you use anywhere else
    - Security audits are ongoing on this codebase. For now, treat it as un-audited.


Running a NuFT Node
-------------------

Stage C | Run the Node (Interactive Method)
-------------------------------------------

1. Connect to Testnet

NuCypher is maintaining a purpose-built endpoint to initially connect to the test network. To connect to the swarm run:

.. code:: bash

    $(nucypher) nucypher ursula run --network <NETWORK_DOMAIN> --teacher <SEEDNODE_URI>
    ...

2. Verify Connection

This will drop your terminal session into the “Ursula Interactive Console” indicated by the ``>>>``.  Verify that the node setup was successful by running the ``status`` command.

.. code::

    Ursula >>> status
    ...

To view a list of known nodes, execute the ``known_nodes`` command

.. code::

    Ursula >>> known_nodes
    ...

You can also view your node’s network status webpage by navigating your web browser to ``https://<your-node-ip-address>:9151/status``.

.. note::

    Since nodes self-sign TLS certificates, you may receive a warning from your web browser.

To stop your node from the interactive console and return to the terminal session

.. code::

    Ursula >>> stop
    ...

Subsequent node restarts do not need the teacher endpoint specified.

.. code:: bash

    (nucypher)$ nucypher ursula run --network <NETWORK_DOMAIN>
    ...

Alternately you can run your node as a system service.
See the *“System Service Method”* section below.


Stage C | Run the Node (System Service Method)
----------------------------------------------
*NOTE - This is an alternative to the “Interactive Method” and assumes you're using systemd.*


1. Create Ursula System Service
    
Use this template to create a file named ``ursula.service`` and place it in ``/etc/systemd/system/``.
    
.. code::

    [Unit]
    Description="Run 'Ursula', a NuCypher Staking Node."
    
    [Service]
    User=<YOUR USER>
    Type=simple
    Environment="NUCYPHER_KEYRING_PASSWORD=<YOUR PASSWORD>"
    ExecStart=<VIRTUALENV PATH>/bin/nucypher ursula run --network <NETWORK_DOMAIN> --teacher <SEEDNODE_URI>
    
    [Install]
    WantedBy=multi-user.target

2. Enable Ursula System Service
    
.. code::

    $ sudo systemctl enable ursula


3. Run Ursula System Service
    
To start Ursula services using systemd
    
.. code::

    $ sudo systemctl start ursula



Check Ursula service status
    
.. code::

    $ sudo systemctl status ursula


To restart your node service
    
.. code::

    $ sudo systemctl restart ursula



Updating a NuFT Node
---------------------

NuCypher is under active development, you can expect frequent code changes to occur as bugs are
discovered and code fixes are submitted. As a result, Ursula nodes will need to be frequently updated
to use the most up-to-date version of the application code.

.. important::

  The steps to update an Ursula running on NuFT are as follows and depends on the type of installation that was employed.


1. Stop the node 

Interactive method
    
.. code::

    Ursula >>> stop

OR

Systemd method
    
.. code::

    $ sudo systemctl stop ursula


2. Update to the latest code version

Update your virtual environment

.. code::

  (nucypher)$ pip3 install -U nucypher


3. Restart Ursula Node
    
Re-activate your environment after updating

Interactive method:

.. code::

    $ source nucypher/bin/activate
    ...
    (nucypher)$ nucypher ursula run --network <NETWORK_DOMAIN>


OR

Systemd Method:

.. code::

    $ sudo systemctl start ursula
