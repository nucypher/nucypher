Finnegan's Wake Demo
====================

.. figure:: https://cdn-images-1.medium.com/max/600/0*b42NPOnflrY07rEf.jpg
    :width: 100%

Overview
--------

.. important::

    This demo requires connecting to a running network. By default the demo is hardcoded to connect to the local demo fleet.


This demo is an example of a NuCypher decentralized network allowing Alice to share
data with Bob using proxy re-encryption. This enables the private sharing of data between
participants in public consensus networks, without revealing data keys to intermediary entities.


+------+-----------+----------------------------------------------------------------------------------------------+
| Step | Character | Operation                                                                                    |
+======+===========+==============================================================================================+
| 1    | Alice     | Alice sets a Policy on the NuCypher network (2-of-3) and grants access to Bob                   |
+------+-----------+----------------------------------------------------------------------------------------------+
| 2    | Alice     | Label and Alice's key public key provided to Bob                                             |
+------+-----------+----------------------------------------------------------------------------------------------+
| 3    | Bob       | Bob joins the policy with Label and Alice's public key                                       |
+------+-----------+----------------------------------------------------------------------------------------------+
| 4    | Enrico    | DataSource created for the policy                                                            |
+------+-----------+----------------------------------------------------------------------------------------------+
| 5    | Enrico    | Each plaintext message gets encapsulated through the DataSource to messageKit                |
+------+-----------+----------------------------------------------------------------------------------------------+
| 6    | Bob       | Bob receives and reconstructs the DataSource from Policy public key and DataSource public key|
+------+-----------+----------------------------------------------------------------------------------------------+
| 7    | Bob       | Bob retrieves the original message form DataSource and MessageKit                            |
+------+-----------+----------------------------------------------------------------------------------------------+


Install Nucypher
----------------

    Acquire the nucypher application code and install the dependencies.
    For a full installation guide see the [NuCypher Installation Guide](../guides/installation_guide).

Download the Book Text
----------------------
    For your convienence we have provided a bash script to acquire the "Finnegan's Wake" text. However,
    feel free to use any text of your choice, as long you you edit the demo code accordingly.

    To run the script:  `./download_finnegans_wake.sh`

Run the Demo
---------------

    After acquiring a text file to re-encrypt, execute the demo by running: `python3 finnegans-wake-demo.py`
