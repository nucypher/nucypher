===========================
Using Environment Variables
===========================

Environment variables are used for configuration in various areas of the codebase to facilitate automation. The
constants for these variables are available in ``nucypher.config.constants``.

Where applicable, values are evaluated in the following order of precedence:

#. CLI parameter
#. Environment variable
#. Configuration file
#. Optional default in code


General
-------

* `NUCYPHER_KEYRING_PASSWORD`
    Password for the `nucypher` Keyring.
* `NUCYPHER_PROVIDER_URI`
    Default Web3 node provider URI.

Alice
-----

* `NUCYPHER_ALICE_ETH_PASSWORD`
    Password for Ethereum account used by Alice.


Ursula (Worker)
---------------

* `NUCYPHER_WORKER_ADDRESS`
    Ethereum account used by Ursula.
* `NUCYPHER_WORKER_IP_ADDRESS`
    IP address of Ursula.
* `NUCYPHER_WORKER_ETH_PASSWORD`
    Password for Ethereum account used by Ursula (Worker).
