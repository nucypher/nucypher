Finnegan's Wake Demo
====================

.. figure:: https://cdn-images-1.medium.com/max/600/0*b42NPOnflrY07rEf.jpg
    :width: 100%

Overview
--------

This demo is an example of a network of PRE nodes allowing Alice to share
data with Bob using proxy re-encryption. This enables the private sharing of data across public consensus networks,
without revealing data keys to intermediary entities.


+------+-----------+----------------------------------------------------------------------------------------------+
| Step | Character | Operation                                                                                    |
+======+===========+==============================================================================================+
| 1    | Alice     | Alice sets a Policy on the PRE Nodes in the Threshold Network and grants access to Bob       |
+------+-----------+----------------------------------------------------------------------------------------------+
| 2    | Alice     | Label and Alice's public key provided to Bob                                                 |
+------+-----------+----------------------------------------------------------------------------------------------+
| 3    | Bob       | Bob joins the policy with Label and Alice's public key                                       |
+------+-----------+----------------------------------------------------------------------------------------------+
| 4    | Enrico    | A data source created for the policy                                                         |
+------+-----------+----------------------------------------------------------------------------------------------+
| 5    | Enrico    | Each plaintext message gets encrypted by Enrico, which results in a messageKit               |
+------+-----------+----------------------------------------------------------------------------------------------+
| 6    | Bob       | Bob receives and reconstructs Enrico from the Policy's public key and Enrico's public key    |
+------+-----------+----------------------------------------------------------------------------------------------+
| 7    | Bob       | Bob retrieves the original message from Enrico and MessageKit                                |
+------+-----------+----------------------------------------------------------------------------------------------+


There are two version of the example, one federated example using a local federated network
and another example using the PRE application development tesnet on Goerli: "Lynx".


Install NuCypher
----------------

Acquire the ``nucypher`` application code and install the dependencies:

.. code::

    $ git clone https://github.com/nucypher/nucypher.git
    ...
    $ python -m venv nucypher-venv
    $ source nucypher-venv/bin/activate
    (nucypher-venv)$ cd nucypher
    (nucypher-venv)$ pip install -e .

Federated Demo
--------------

First run the local federated network:

.. code::

    python ../run_demo_ursula_fleet.py

Then run the demo:

.. code::

    python finnegans-wake-demo-federated.py

Testnet Demo
------------

First, configure the demo.  Be sure tat alice's address has some Goerli ETH.

.. code::

    export DEMO_ETH_PROVIDER_URI=<GOERLI RPC ENDPOINT>
    export DEMO_ALICE_ETH_ADDRESS=<ETH ADDRESS>
    export DEMO_SIGNER_URI=keystore://<PATH TO KEYSTORE>

Then run the demo:

.. code::

    python finnegans-wake-demo-testnet.py
