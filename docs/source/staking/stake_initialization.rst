.. _staking-guide:

Stake Initialization
====================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Stakers.


Staking Requirements
---------------------

The staking CLI itself is lightweight and can be run on commodity hardware. While there are no
specific minimum system constraints, there are some basic requirements for stakers:

#. Hosted or Remote Ethereum Node (Infura, Geth, etc.)
#. Hardware or Software Wallet (Trezor, Ledger, Keyfile)
#. At least 15,000 NU
#. Small amount of ether to pay for transaction gas

Using a hardware wallet is *highly* recommended. They are ideal for stakers since they hold NU and
temporary access to private keys is required during stake management, while providing a higher standard
of security than software wallets or keyfiles.


Staking Procedure
-----------------

#. Obtain and secure NU
#. Install ``nucypher`` on Staker's system (pip :doc:`/references/pip-installation` and docker are supported)
#. Configure nucypher CLI for staking (`3. Configure nucypher for staking`_)
#. Bond a Worker to your Staker using the worker's ethereum address (see `6. Bond a worker`_)
#. Manage active stakes (:doc:`stake_management`)

.. caution::

    Once NU is locked in the staking escrow contract, a worker node must be run to unlock it.  Worker's make
    periodic automated commitments (every 7 days) which cost at least ~200k gas, depending on how many sub-stakes
    you have. Be sure to consider this operational cost when locking NU.

.. note::

    If you are running an Ibex testnet node, testnet tokens can be obtained by joining the
    `Discord server <https://discord.gg/7rmXa3S>`_ and typing ``.getfunded <YOUR_STAKER_ETH_ADDRESS>``
    in the #testnet-faucet channel.


1. Establish an Ethereum Provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Staking transactions can be broadcasted using either a local or remote ethereum node.

For general background information about choosing a node technology and operation,
see https://web3py.readthedocs.io/en/stable/node.html.


2. Select Transaction Signer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, all transaction and message signing requests are forwarded to the configured ethereum provider.
When using an external ethereum provider (e.g. Infura, Alchemy, other hosted/remote node), a local transaction signer must
be configured in addition to the broadcasting node. This can be a hardware wallet, software wallet, or clef.

For more detailed information see :doc:`/references/signers`

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer <SIGNER_URI>

.. note::

    For hardware wallets, only trezor is currently supported by the CLI directly.
    Ledger functionality can be achieved through clef.


Trezor Signer (Recommended)
++++++++++++++++++++++++++++

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer trezor

Keystore File Signer
++++++++++++++++++++

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer keystore://<ABSOLUTE PATH TO KEYFILE>

.. danger::

    The Keystore signer is not safe to use for mainnet :ref:`Staker operations <staking-guide>`
    (An exception can be made for testnets). For staking operations use a hardware wallet.

Clef Signer
+++++++++++

Clef can be used as an external transaction signer with nucypher and supports both hardware (ledger & trezor)
and software wallets. See :ref:`signing-with-clef` for setting up Clef. By default, all requests to the clef
signer require manual confirmation.

This includes not only transactions but also more innocuous requests such as listing the accounts
that the signer is handling. This means, for example, that a command like ``nucypher stake accounts`` will first ask
for user confirmation in the clef CLI before showing the Staker accounts. You can automate this confirmation by
using :ref:`clef-rules`.

.. note::

    The default location for the clef IPC file is ``/home/<username>/.clef/clef.ipc``
    (on MacOS, ``/Users/<username>/Library/Signer/clef.ipc``)

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer clef://<CLEF IPC PATH> --hw-wallet

    # Create a new stakeholder with clef as the default signer
    $ nucypher stake init-stakeholder --signer clef:///home/<username>/.clef/clef.ipc ...

    # Update an existing configuration with clef as the default signer
    $ nucypher stake config --signer clef:///home/<username>/.clef/clef.ipc  # Set clef as the default signer

    # Create a new stake using inline signer and provider values
    $ nucypher stake create --signer clef:///home/<username>/.clef/clef.ipc --provider ~/.ethereum/geth.ipc


3. Configure nucypher for staking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before initiating a stake, a setup step is required to configure nucypher for staking.
This will create a JSON configuration file (`~/.local/share/nucypher/stakeholder.json`) containing editable
configuration values.  No new keys or secrets are created in this step, it is just for configuration.

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --signer <SIGNER URI> --provider <PROVIDER>

.. note:: If you are using NuCypher's Ibex testnet, passing the network name is required ``--network ibex``.


4. Create a new stake
~~~~~~~~~~~~~~~~~~~~~~

Once you have configured nucypher for staking, you can proceed with stake initiation.
This operation will transfer NU to nucypher's staking escrow contract, locking it for
the commitment period.


.. caution::

    Before proceeding it is important to know that the worker must spend ETH to unlock staked NU.
    Once tokens are locked, the only way for them to become unlocked is by running a bonded Worker node.

    Currently, Worker nodes must perform one automated transaction every 7 days costing ~200k gas.


.. code:: bash


    (nucypher)$ nucypher stake create
    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):
    Enter stake value in NU (15000 NU - 45000 NU) [45000]: 45000
    Enter stake duration (4 - 62863) [52]: 4

    ══════════════════════════════ STAGED STAKE ══════════════════════════════

    Staking address: 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf
    ~ Chain      -> ID # <CHAIN_ID>
    ~ Value      -> 45000 NU (45000000000000000000000 NuNits)
    ~ Duration   -> 28 Days (4 Periods)
    ~ Enactment  -> Mar 24 2021 17:00 PDT (period #2673)
    ~ Expiration -> Apr 21 2021 17:00 PDT (period #2677)

    ═════════════════════════════════════════════════════════════════════════

    * Ursula Node Operator Notice *
    -------------------------------

    By agreeing to stake 45000 NU (45000000000000000000000 NuNits):

    - Staked tokens will be locked for the stake duration.

    - You are obligated to maintain a networked and available Ursula-Worker node
      bonded to the staker address 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf for the duration
      of the stake(s) (4 periods).

    - Agree to allow NuCypher network users to carry out uninterrupted re-encryption
      work orders at-will without interference.

    Failure to keep your node online or fulfill re-encryption work orders will result
    in loss of staked NU as described in the NuCypher slashing protocol:
    https://docs.nucypher.com/en/latest/architecture/slashing.html.

    Keeping your Ursula node online during the staking period and successfully
    producing correct re-encryption work orders will result in rewards
    paid out in ethers retro-actively and on-demand.

    Accept ursula node operator obligation? [y/N]: y
    Publish staged stake to the blockchain? [y/N]: y
    Broadcasting APPROVEANDCALL Transaction (0.0821491982 ETH @ 261.575 gwei)
    TXHASH 0xf4fc7d6b674c83e4fd99fef64e194b7455fc4438a639e2973b09f09f3493ad10
    Waiting 600 seconds for receipt

    Stake initialization transaction was successful.
    ...

    StakingEscrow address: 0x40Ca356d8180Ddc21C82263F9EbCeaAc6Cad7250

    View your stakes by running 'nucypher stake list'
    or set your Ursula worker node address by running 'nucypher stake bond-worker'.

    See https://docs.nucypher.com/en/latest/staking/running_a_worker.html


You will need to confirm two transactions here.


5. List existing stakes
~~~~~~~~~~~~~~~~~~~~~~~

Once you have created one or more stakes, you can view all active stakes for connected wallets:

.. code:: bash

    (nucypher)$ nucypher stake list

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker not bonded ════
    --------------  -----------------------------------
    Status          Never Made a Commitment (New Stake)
    Restaking       Yes
    Winding Down    No
    Snapshots       Yes
    Unclaimed Fees  0 ETH
    Min fee rate    50 gwei
    --------------  -----------------------------------
    ╒═══════╤══════════╤═════════════╤═════════════╤═══════════════╤════════╤═══════════╕
    │  Slot │ Value    │   Remaining │ Enactment   │ Termination   │  Boost │ Status    │
    ╞═══════╪══════════╪═════════════╪═════════════╪═══════════════╪════════╪═══════════╡
    │     0 │ 45000 NU │           5 │ Mar 24 2021 │ Apr 21 2021   │  1.10x │ DIVISIBLE │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛

.. caution::
    If the Worker in the list is shown as ``NO_WORKER_BONDED``,
    it means that you haven't yet bonded a Worker node to your Staker.
    Your staking account will be highlighted in red.


.. _bond-worker:

6. Bond a Worker
~~~~~~~~~~~~~~~~~

After initiating a stake, the staker must delegate access to a work address through *bonding*.
There is a 1:1 relationship between the roles: A Staker may have multiple substakes but only ever has one Worker at a time.

.. important:: The Worker cannot be changed for a minimum of 2 periods (14 days) once bonded.

.. code:: bash

    (nucypher)$ nucypher stake bond-worker
    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):
    Enter worker address: 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10
    Commit to bonding worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 to staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf for a minimum of 2 periods? [y/N]: y
    ...
    This worker can be replaced or detached after period #2674 (2021-04-01 00:00:00+00:00)


.. note::

    The worker's address must be EIP-55 checksum valid, however, geth shows addresses in the lowercase
    normalized format. You can convert the normalized address to checksum format on etherscan or using the geth console:

    .. code:: bash

        $ geth attach ~/.ethereum/geth.ipc
        > eth.accounts
        ["0x63e478bc474ebb6c31568ff131ccd95c24bfd552", "0x270b3f8af5ba2b79ea3bd6a6efc7ecab056d3e3f", "0x45d33d1ff0a7e696556f36de697e5c92c2cccfae"]
        > web3.toChecksumAddress(eth.accounts[2])
        "0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE"


After this step, you're finished with the Staker, and you can proceed to :ref:`ursula-config-guide`.
