NuCypher
========
*A proxy re-encryption network to empower privacy in decentralized systems*


----

.. image:: https://img.shields.io/pypi/v/nucypher.svg?style=flat
    :target: https://pypi.org/project/nucypher/

.. image:: https://img.shields.io/pypi/pyversions/nucypher.svg
    :target: https://pypi.org/project/nucypher/

.. image:: https://img.shields.io/circleci/project/github/nucypher/nucypher.svg?logo=circleci
    :target: https://circleci.com/gh/nucypher/nucypher/tree/master
    :alt: CircleCI build status

.. image:: https://codecov.io/gh/nucypher/nucypher/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/nucypher/nucypher

.. image:: https://img.shields.io/discord/411401661714792449.svg?logo=discord
    :target: https://discord.gg/7rmXa3S
    :alt: Discord

.. image:: https://readthedocs.org/projects/nucypher/badge/?version=latest
    :target: https://nucypher.readthedocs.io/en/latest/
    :alt: Documentation Status

.. image:: https://img.shields.io/pypi/l/nucypher.svg
    :target: https://www.gnu.org/licenses/gpl-3.0.html

.. _Umbral: https://github.com/nucypher/pyUmbral

The NuCypher network facilitates end-to-end encrypted data sharing
for distributed apps and protocols.
Access permissions are baked into the underlying encryption,
and access can only be explicitly granted by the data owner via sharing policies.
Consequently, the data owner has ultimate control over access to their data.
At no point is the data decrypted nor can the underlying private keys be
determined by the NuCypher network.

Under the hood, the NuCypher network uses the Umbral_
threshold proxy re-encryption scheme to provide cryptographic access control.

How does NuCypher work?
-----------------------

1. Alice, the data owner, grants access to her encrypted data to
anyone she wants by creating a policy and uploading it to
the NuCypher network.

2. Using her policy's public key, any entity can encrypt data on Alice's behalf.
This entity could be an IoT device in her car, a collaborator assigned
the task of writing data to her policy, or even a third-party creating
data that belongs to her – for example, a lab analyzing medical tests.
The resulting encrypted data can be uploaded to IPFS, Swarm, S3,
or any other storage layer.

3. A group of Ursulas, which are nodes of the NuCypher network,
receive the access policy and stand ready to
re-encrypt data in exchange for payment in fees and token rewards.
Thanks to the use of proxy re-encryption,
Ursulas and the storage layer never have access to Alice's plaintext data.

4. Bob, a data recipient, sends an access request to the NuCypher network.
If the policy is satisfied, the data is re-encrypted to his public key
and he can decrypt it with his private key.

More detailed information:

- GitHub https://www.github.com/nucypher/nucypher
- Website https://www.nucypher.com/


Whitepapers
-----------

**Network**

    https://github.com/nucypher/whitepaper/blob/master/whitepaper.pdf

    *"NuCypher - A proxy re-encryption network to empower privacy in decentralized systems"*
    *by Michael Egorov, David Nuñez, and MacLane Wilkison - NuCypher*


**Economics**

    https://github.com/nucypher/mining-paper/blob/master/mining-paper.pdf

    *"NuCypher - Mining & Staking Economics"*
    *by Michael Egorov, MacLane Wilkison - NuCypher*


**Cryptography**

    https://github.com/nucypher/umbral-doc/blob/master/umbral-doc.pdf

    *"Umbral A Threshold Proxy Re-Encryption Scheme"*
    *by David Nuñez - NuCypher*


.. warning::

   NuCypher is currently in the *Alpha* development stage and is **not** intended for use in production.


.. toctree::
   :maxdepth: 1
   :caption: Guides

   guides/quickstart
   guides/federated_testnet_guide
   guides/installation_guide
   guides/ursula_configuration_guide
   guides/contribution_guide
   guides/character_control_guide
   guides/staking_guide
   guides/deployment_guide

.. toctree::
   :maxdepth: 1
   :caption: Demos

   demos/local_fleet_demo
   demos/finnegans_wake_demo
   demos/heartbeat_demo

.. toctree::
   :maxdepth: 1
   :caption: Architecture

   architecture/contracts
   architecture/upgradeable_proxy_contracts
   architecture/slashing

.. toctree::
   :maxdepth: 1
   :caption: API

   api/characters
   api/config
   api/crypto
   api/keyring
   api/keystore
   api/network
   api/policy

.. toctree::
   :maxdepth: 1
   :caption: Release Notes

   release_notes/genesis_release


Indices and Tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
