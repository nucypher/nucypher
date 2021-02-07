================
Worker Diligence
================

.. attention::

    This best practices document is a work-in-progress and is not comprehensive.


Workers can demonstrate their vested interest in the success of the network by adhering to
three core areas of responsibility (in order of importance):

1. Keystore Diligence
---------------------

Requires that private keys used by the worker are backup or can be restored.

Keystore diligence an be exercised by:

  - Backing up the worker's private keys (both ethereum and nucypher).
  - Using a password manager to generate a strong password when one is required.

.. note::

    The default location of the nucypher worker keystore files can be located by
    running a nucypher command:

    .. code::

        $ nucypher --config-path

    Encrypted worker keys can be found in the ``keyring`` directory:

    .. code-block:: bash

        /home/user/.local/share/nucypher
        ├── ursula.json
        ├── keyring
        │   ├── private
        │   │   ├── delegating-0x12304EF1Dc04587225FEe3420CA6C786cdd58893.priv
        │   │   ├── root-0x12304EF1Dc04587225FEe3420CA6C786cdd58893.priv
        │   │   └── signing-0x12304EF1Dc04587225FEe3420CA6C786cdd58893.priv
        │   └── public
        │       ├── root-0x12304EF1Dc04587225FEe3420CA6C786cdd58893.pub
        │       └── signing-0x12304EF1Dc04587225FEe3420CA6C786cdd58893.pub
        └── ...

2. Datastore Diligence
----------------------

Requires that material observed during the runtime be stored.

A running worker stores peer metadata, re-encryption key fragments ("Kfrags"), and "treasure maps".

Loss of stored re-encryption key fragments will lead to slashing of the bonded stake.
If a worker node has already agreed to enforce a policy, then loses a Kfrag, network users
can issue a challenge which is verified onchain by the Adjudicator contract.

As a civic matter, storing node validity status is important for workers so that they refrain from
pestering nodes with unnecessary additional verification requests. Loss of peer metadata means
that the worker must rediscover and validate peers, slowly rebuilding its network view which contributes to
lessened availability and higher network-wide traffic.

Datastore diligence can be exercised by maintain regular backups of the worker's filesystem and database.


.. note::

    The default location of the worker keystore files can be located by running a nucypher command:

    .. code-block:: bash

        $ nucypher --config-path

    The worker database and peer metadata can be found in the nucypher configuration root

    .. code-block:: bash

        /home/user/.local/share/nucypher
        ├── ursula.db
        │   ├── ...
        └── known_nodes
            ├── certificates
            |   └── ...
            └── metadata
                └── ...


3. Runtime Diligence
--------------------

Requires active and security-conscious participation in the network.

A bonded node that is unreachable or otherwise invalid will be unable to accept new
policies, and miss out on inflation rewards.  The bonded stake will remain locked until
the entire commitment is completed.

The worker's ethereum account must have enough ether to pay for transaction gas;
however, it is *not* necessary (and potentially risky) to hold NU tokens on a worker's
account for any reason.

Runtime Diligence an be exercised by:

- Secure the worker's keystore used on the deployment host.
- Maintain high uptime; keep downtime brief when required by updates or reconfiguration.
- Update when a new version is available.
- Monitor a running ursula for nominal behaviour and period confirmations.
- Hold enough ETH in the worker's ethereum wallet to pay for gas.


..
    TODO: separate section on backups and data (#2285)
