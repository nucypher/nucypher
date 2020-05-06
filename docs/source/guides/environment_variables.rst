===========================
Using Environment Variables
===========================

Environment variables are used for configuration in various areas of the codebase to facilitate automation. The
constants for these variables are available in ``nucypher.config.constants``.

General
-------

* `NUCYPHER_KEYRING_PASSWORD`
    Password for the `nucypher` Keyring.
* `NUCYPHER_PROVIDER_URI`
    Default Web3 node provider URI. Only used if the provider URI is not explicitly provided.


Alice
-----

* `NUCYPHER_ALICE_ETH_PASSWORD`
    Password for Ethereum account used by Alice.


Ursula (Worker)
---------------

* `NUCYPHER_WORKER_ADDRESS`
    Ethereum account used by Ursula. Only used if the account address is not explicitly provided.
* `NUCYPHER_WORKER_IP_ADDRESS`
    IP address of Ursula. Only used if the IP address is not explicitly provided.
* `NUCYPHER_WORKER_ETH_PASSWORD`
    Password for Ethereum account used by Ursula (Worker).





