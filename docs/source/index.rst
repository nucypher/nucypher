NuCypher
========
*A decentralized cryptological network offering accessible, intuitive, and extensible runtimes and interfaces for secrets management and dynamic access control.*


----

.. image:: https://img.shields.io/pypi/v/nucypher.svg?style=flat
    :target: https://pypi.org/project/nucypher/

.. image:: https://img.shields.io/pypi/pyversions/nucypher.svg
    :target: https://pypi.org/project/nucypher/

.. image:: https://img.shields.io/circleci/project/github/nucypher/nucypher.svg?logo=circleci
    :target: https://circleci.com/gh/nucypher/nucypher/tree/main
    :alt: CircleCI build status

.. image:: https://codecov.io/gh/nucypher/nucypher/branch/main/graph/badge.svg
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

The NuCypher network provides accessible, intuitive, and extensible runtimes and interfaces for secrets management and dynamic access control.

* Accessible - The network is permissionless and censorship-resistant.
  There are no gate-keepers and anyone can use it.
* Intuitive - The network leverages the classic cryptological narrative of Alice and Bob
  (with additional characters where appropriate). This character-based narrative permeates the code-base and helps
  developers write safe, misuse-resistant code.
* Extensible - The network currently supports proxy re-encryption but can be extended to provide support for other cryptographic primitives.

Access permissions are baked into the underlying encryption,
and access can only be explicitly granted by the data owner via sharing policies.
Consequently, the data owner has ultimate control over access to their data.
At no point is the data decrypted nor can the underlying private keys be
determined by the NuCypher network.

Under the hood, the NuCypher network uses the Umbral_
threshold proxy re-encryption scheme to provide cryptographic access control.

How does NuCypher work?
-----------------------

.. image:: ./.static/img/nucypher_overview.svg
    :target: ./.static/img/nucypher_overview.svg

1. Alice, the data owner, grants access to her encrypted data to
anyone she wants by creating a policy and uploading it to
the NuCypher network.

2. A group of Ursulas, which are nodes on the NuCypher network,
receive information about the policy, called a PolicyArrangement that include
a re-encryption key share. The Ursulas stand ready to re-encrypt data in exchange for payment
in fees and token rewards. Thanks to the use of proxy re-encryption,
Ursulas and the storage layer never have access to Alice's plaintext data.

3. Each policy created by Alice has an associated encryption key, which can be used
by any entity (Enrico) to encrypt data on Alice's behalf.
This entity could be an IoT device in her car, a collaborator assigned
the task of writing data to her policy, or even a third-party creating
data that belongs to her – for example, a lab analyzing medical tests.
The resulting encrypted data can be uploaded to IPFS, Swarm, S3,
or any other storage layer.

4. Bob, a data recipient, obtains the encrypted data from the storage layer and sends an access request
to the NuCypher network. If the policy is satisfied, the data is re-encrypted to his public key
and he can decrypt it with his private key.

5. Ursulas earn fees and token rewards for performing
re-encryption operations.

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

    https://github.com/nucypher/whitepaper/blob/master/economics/staking_protocol/NuCypher_Staking_Protocol_Economics.pdf

    *"NuCypher Network: Staking Protocol & Economics"*
    *by Michael Egorov, MacLane Wilkison, Arjun Hassard - NuCypher*


    https://github.com/nucypher/whitepaper/blob/master/economics/pricing_protocol/NuCypher_Network__Pricing_Protocol_Economics.pdf

    *"NuCypher Network: Pricing Protocol & Economics"*
    *by Arjun Hassard - NuCypher*


**Cryptography**

    https://github.com/nucypher/umbral-doc/blob/master/umbral-doc.pdf

    *"Umbral A Threshold Proxy Re-Encryption Scheme"*
    *by David Nuñez - NuCypher*


.. warning::

   NuCypher is currently in the *Beta* development stage and is **not** intended for use in production.


.. toctree::
   :maxdepth: 1
   :caption: Guides

   guides/installation_guide
   guides/network_node/network_node
   guides/development/development
   guides/ethereum_node
   guides/worklock_guide
   guides/dao_guide
   guides/environment_variables
   guides/contribution_guide

.. toctree::
   :maxdepth: 1
   :caption: Demos

   demos/local_fleet_demo
   demos/finnegans_wake_demo
   demos/heartbeat_demo

.. toctree::
   :maxdepth: 1
   :caption: Architecture

   architecture/character
   architecture/worklock
   architecture/contracts
   architecture/upgradeable_proxy_contracts
   architecture/dao
   architecture/sub_stakes
   architecture/slashing
   architecture/service_fees

.. toctree::
   :maxdepth: 1
   :caption: API

   api/nucypher.blockchain
   api/nucypher.characters
   api/nucypher.config
   api/nucypher.policy
   api/nucypher.network
   api/nucypher.datastore
   api/nucypher.crypto
   api/nucypher.acumen

.. toctree::
   :maxdepth: 1
   :glob:
   :caption: Contracts API

   contracts_api/index

.. toctree::
   :maxdepth: 1
   :caption: Release Notes

   release_notes/genesis_release
   release_notes/pre_release_epics
   release_notes/releases.rst

.. toctree::
   :maxdepth: 1
   :caption: Glossary

   glossary

.. toctree::
   :maxdepth: 1
   :caption: Support

   support/node_providers
   support/community
   support/troubleshooting
   support/faq


Indices and Tables
==================
* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
