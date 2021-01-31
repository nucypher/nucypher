Finnegan's Wake Demo
====================

.. figure:: https://cdn-images-1.medium.com/max/600/0*b42NPOnflrY07rEf.jpg
    :width: 100%

Overview
--------

This demo is an example of a NuCypher decentralized network allowing Alice to share
data with Bob using proxy re-encryption. This enables the private sharing of data across public consensus networks,
without revealing data keys to intermediary entities.


+------+-----------+----------------------------------------------------------------------------------------------+
| Step | Character | Operation                                                                                    |
+======+===========+==============================================================================================+
| 1    | Alice     | Alice sets a Policy on the NuCypher network (2-of-3) and grants access to Bob                |
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


Run a fleet of federated Ursulas
--------------------------------
    Run the local fleet of federated Ursulas in a separate terminal. This provides a network of 12 federated
    Ursulas.

.. code::

    (nucypher)$ python examples/run_demo_ursula_fleet.py

Download the Book Text
----------------------
    For your convenience we have provided a bash script to acquire the "Finnegan's Wake" text. However,
    feel free to use any text of your choice, as long you you edit the demo code accordingly.

    To run the script from the ``examples/finnegans_wake_demo`` directory:

.. code::

    (nucypher)$ ./download_finnegans_wake.sh

Run the Demo
---------------

    After acquiring a text file to re-encrypt, execute the demo from the ``examples/finnegans_wake_demo`` by running:

.. code::

    (nucypher)$ python finnegans-wake-demo.py
