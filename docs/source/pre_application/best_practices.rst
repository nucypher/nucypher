=======================
Node/Operator Diligence
=======================

.. attention::

    This best practices document is a work-in-progress and is not comprehensive.


Operators can demonstrate their vested interest in the success of the network by adhering to
the following core areas of responsibility (in order of importance):

1. Keystore Diligence
---------------------

Requires that private keys used by the worker are backed up and can be restored.

Keystore diligence an be exercised by:

  - Keeping an offline record of the mnemonic recovery phrase.
  - Backing up the worker's keystores (both ethereum and nucypher).
  - Using a password manager to generate and store a strong password when one is required.

.. note::

    The default location of the nucypher worker keystore files can be located by
    running a nucypher command:

    .. code::

        $ nucypher --config-path

    Encrypted worker keys can be found in the ``keystore`` directory:

    .. code-block:: bash

        /home/user/.local/share/nucypher
        ├── ursula.json
        ├── keystore
        │   ├── 1621399628-e76f101f35846f18d80bfda5c61e9ec2.priv
        └── ...

2. Runtime Diligence
--------------------

Requires active and security-conscious participation in the network.

A PRE node that is unreachable or otherwise invalid will be unable to accept new
policies, and miss out on inflation rewards.

It is *not* necessary (and potentially risky) to hold NU/T tokens on an Operator's
account for any reason.

Runtime Diligence an be exercised by:

- Secure the node's keystore used on the deployment host.
- Maintain high uptime; keep downtime brief when required by updates or reconfiguration.
- Update when a new version is available.

..
    TODO: separate section on backups and data (#2285)
