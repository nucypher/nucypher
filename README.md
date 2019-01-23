NuCypher
========
*A proxy re-encryption network to empower privacy in decentralized systems*

- Website https://www.nucypher.com/
- GitHub https://www.gihub.com/nucypher/nucypher


.. image:: https://circleci.com/gh/nucypher/nucypher/tree/master.svg?style=svg
    :target: https://circleci.com/gh/nucypher/nucypher/tree/master

.. image:: https://coveralls.io/repos/github/nucypher/nucypher/badge.svg?branch=master
    :target: https://coveralls.io/github/nucypher/nucypher?branch=master



NuCypher Proxy Re-encryption Network
-------------------------------------

1. Alice, the data owner, encrypts data with her public key and uploads it to IPFS, Swarm, S3, or any supported storage layer.
To delegate access to valid recipients, she creates and uploads re-encryption keys to the NuCypher network.


2. Ursula, a miner, receives the re-encryption keys and stands ready to re-key data.
She provides this service in exchange for payment in fees and block rewards.
The NuCypher network and the storage layer never have access to Alice's plaintext data.


3. Bob, a valid recipient, sends an access request to the NuCypher network.
If a valid re-encryption key exists and specified conditions are met,
the data is re-keyed to his public key and he is able to decrypt with his private key.


Whitepapers
-----------

**Network**

https://www.nucypher.com/static/whitepapers/english.pdf

*NuCypher - A proxy re-encryption network to empower privacy in decentralized systems*
*Michael Egorov, David Nuñez, and MacLane Wilkison - NuCypher*


**Economics**

https://www.nucypher.com/static/whitepapers/mining-paper.pdf

*NuCypher - Mining & Staking Economics*
*Michael Egorov, MacLane Wilkison - NuCypher*


.. toctree::
   :maxdepth: 2


Architecture
------------

.. toctree::
   :maxdepth: 1

   architecture/contracts
   architecture/upgradeable_proxy_contracts


Guides
------

.. toctree::
   :maxdepth: 2

   guides/quickstart
   guides/federated_testnet_guide
   guides/installation_guide
   guides/contribution_guide


Demos
-----

.. toctree::
   :maxdepth: 2

   demos/local_fleet_demo
   demos/finnegans_wake_demo
   demos/heartbeat_demo


API
---

.. toctree::
   :maxdepth: 2

   api/characters
   api/config
   api/crypto
   api/keyring
   api/keystore
   api/network
   api/policy


Release Notes
-------------

.. toctree::
   :maxdepth: 1

   release_notes/genesis_release


Indices and Tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
