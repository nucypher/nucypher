Alice & Bob CLI
=================

Overview
--------

This guide is an example of NuCypher's decentralized network allowing Alice to share a secret
with Bob using the NuCypher Network via the ``nucypher`` CLI. It is analogous to the ``python`` example
in :doc:`/application_development/getting_started`.

.. note::

    While the example provided uses Ethereum mainnet, these steps can be followed for the Rinkeby Testnet
    with updated `geth` (``~/.ethereum/rinkeby/geth.ipc``) and `seed` URI (``https://ibex.nucypher.network:9151``).


To better understand the commands and their options, use the ``--help`` option.


Initialize Testnet Alice and Bob
---------------------------------

.. code::

    # Create a new Alice
    (nucypher)$ nucypher alice init --provider <PROVIDER URI> --signer <SIGNER URI> --network lynx

    # Create a new Bob
    (nucypher)$ nucypher bob init --provider <PROVIDER URI> --signer <SIGNER URI> --network lynx

Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string on the goerli ethereum network, for example:

    - ``ipc:///home/<username>/.ethereum/geth.ipc`` - IPC Socket-based JSON-RPC server (Geth)
    - ``https://<host>`` - HTTP(S)-based JSON-RPC server


Get Bob's Public Keys
---------------------
.. code::

    (nucypher)$ nucypher bob public-keys

Output:

.. code::

    bob_encrypting_key ...... 0202a6be8e400acdd50db42f8b4c62241b61461a08462731efc064b86d63c7cf6f
    bob_verifying_key ...... 02ce770f45fecbbee0630129cce0da4fffc0c4276093bdb3f83ecf1ed824e2696c


Alice Grants Access To Secret
-----------------------------
.. code::

    (nucypher)$ nucypher alice grant \
    >     --bob-verifying-key 02ce770f45fecbbee0630129cce0da4fffc0c4276093bdb3f83ecf1ed824e2696c \
    >     --bob-encrypting-key 0202a6be8e400acdd50db42f8b4c62241b61461a08462731efc064b86d63c7cf6f \
    >     --label <LABEL> \
    >     --expiration 2019-12-20T10:07:50Z \
    >     -m 1 -n 1 --value 1 --debug

Output:

.. code::

    treasure_map ...... dAYjo1M+OWFWXS/EkRGGBUJ6ywgGczmbELGbncfYT1W51k/EBO6y/LwSIeoQcrT/NzE25OXnsnnwOzwoZxT5oE7fhO+HbJPiGTt1Fl4iCvVrwxuJWIk0Nrw9WslSNBzAAAABHAM2ndUrO/67tZnGmF8ca1U8h09k2Qsn3gohnEP2M4aIfwPxG9F2jOqSS7OVoBsNnziS0qdYqMXmPPMnNrUPyR4PfB+9RmvtufpZ1DbbP4MEyxL1qL4xrmNhr6AYSMbnJD6FA3Qb0AGzgLrvTrO7qaWSJ2mxKMyGNnC/FeZhjg4AeuTfuEGEkogqeL/uMTNrl5vG3JwNIXFVsPY3sXR743ZKpP4ypu8HFj8BoqSfxleRmcwbANHQlSdwBd+/NJLcdqQCVuB1UdFDJPCJ3HxvjHIRhxWHTtuQ4L/HIjxTHoRsS/CFwjembIWhqpxqfswnxmKRQ5hCosO6iqK3aRYkDpOQMPwqgkv0diRBx5AC7Fj1nSfuXlpJix8PLxcy
    policy_encrypting_key ...... 021664726f939a8e79df4f4b737da2dd78d1c0fea106d19d6fce4df678e552c561
    alice_verifying_key ...... 03741bd001b380baef4eb3bba9a5922769b128cc863670bf15e6618e0e007ae4df


Enrico Encrypts Secret
----------------------

.. code::

    (nucypher)$ nucypher enrico encrypt \
    >     --policy-encrypting-key 021664726f939a8e79df4f4b737da2dd78d1c0fea106d19d6fce4df678e552c561 \
    >     --message "Peace at Dawn"

Output:

.. code::

    message_kit ...... ApZrJG9HOoNM7F6YZiiMhjRmWcMWP3rKmNLrsuAwdxh7A1cMPdJ5wppSU3LUgmvbJMiddZzsJKw0iJ1Vn1ax4TsmRqSKyR5NBEescZjTzX8fn7wzfwL0Q/vyIL9XFCi3nHACaNPrLk8yON7fAD/LDndn9BrdBRtM3lEXJ43tesa+v/g7i1uQ7HqAp2SDtQTrqyWQ3oc3xx0+TDN2ASvlYm+yed1/B3EM1I/ItghTsrDegoroVeYQbeTEbbs+PR9OgPyLUoXmDricfc6OdTaYZh4ZviXo6XpTPboQ6tv32pDqmoVY8TkPSmPkq5ZC7dD9SeModP92/A==
    signature ...... 6bE86KVxKdhX7fmXnfg9ym7aUgxl9seQcOAq2cMzJ7saJjD8lFMqmJ5gFToqJF341GUy+BdUMQiXMqpwrwivoA==


Bob Retrieves And Decrypts Secret
---------------------------------

.. code::

    (nucypher)$ nucypher bob retrieve \
    >     --label <LABEL> \
    >     --message-kit ApZrJG9HOoNM7F6YZiiMhjRmWcMWP3rKmNLrsuAwdxh7A1cMPdJ5wppSU3LUgmvbJMiddZzsJKw0iJ1Vn1ax4TsmRqSKyR5NBEescZjTzX8fn7wzfwL0Q \
    >     --policy-encrypting-key 021664726f939a8e79df4f4b737da2dd78d1c0fea106d19d6fce4df678e552c561 \
    >     --alice-verifying-key 03741bd001b380baef4eb3bba9a5922769b128cc863670bf15e6618e0e007ae4df \

Output:

.. code::

    cleartexts ...... ['UGVhY2UgYXQgRGF3bg==']

The resulting cleartext is ``"Peace at Dawn"`` in base64:

.. code::

    (nucypher)$ echo UGVhY2UgYXQgRGF3bg== | base64 -d
    Peace at Dawn
