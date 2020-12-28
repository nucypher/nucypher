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
only temporary access to private keys is required during stake management while providing a higher standard
of security than software wallets or keyfiles.


Staking Procedure
-----------------

#. Obtain and Secure NU
#. Install ``nucypher`` on Staker's system (:doc:`/guides/installation`)
#. Configure nucypher CLI for staking (`3. Configure nucypher for staking`_)
#. Bond a Worker to your Staker using the worker's ethereum address (see `6. Bond a worker`_)
#. Manage active stakes (:doc:`stake_management`)

.. important::

    Once NU is locked in the staking escrow contract, a worker node must be run to unlock it.

.. note::

    If you are running a testnet node, Testnet tokens can be obtained by joining the
    `Discord server <https://discord.gg/7rmXa3S>`_ and typing ``.getfunded <YOUR_STAKER_ETH_ADDRESS>``
    in the #testnet-faucet channel.


1. Establish an ethereum provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Staking transactions can be broadcasted using either a local or remote ethereum node.

For general background information about choosing a node technology and operation,
see https://web3py.readthedocs.io/en/stable/node.html.


2. Select transaction signer
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

By default, all transaction and message signing requests are forwarded to the configured ethereum provider.
To use a remote ethereum provider (e.g. Infura, Alchemy, Another Remote Node) a local transaction signer must
be configured in addition to the broadcasting node.  This can be a hardware wallet, software wallet, or clef.

For more detailed information see :doc:`../signers`

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer <SIGNER_URI>

.. note::

    Currently Only trezor hardware wallets are supported by the CLI directly.  Ledger functionality can be achieved
    through clef.


Trezor Signer
+++++++++++++

This is the top recommendation.

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer trezor

Keystore File Signer
++++++++++++++++++++

Not recommended for mainnet.

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer keystore://<ABSOLUTE PATH TO KEYFILE>


Clef Signer
+++++++++++

Clef can be used as an external transaction signer with nucypher supporting both hardware (ledger & trezor)
and software wallets. See :ref:`signing-with-clef` for setting up Clef. By default, all requests to the clef
signer require manual confirmation.

This includes not only transactions but also more innocuous requests such as listing the accounts
that the signer is handling. This means, for example, that a command like ``nucypher stake accounts`` will first ask
for user confirmation in the clef CLI before showing the staker accounts. You can automate this confirmation by
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

Before continuing with stake initiation, A setup step is required to configure nucypher for staking.
This will create a JSON configuration file (`~/.local/share/nucypher/stakeholder.json`) containing editable
configuration values.  No new keys or secrets are created in this step, it's just for configuration.

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --signer <SIGNER URI> --provider <PROVIDER>

.. note:: If you are using NuCypher's Rinkeby testnet, passing the network name is rquired ``--network ibex``.


4. Create a new stake
~~~~~~~~~~~~~~~~~~~~~~

Once you have configured nucypher for staking, you can proceed with stake initiation.
This operation will transfer NU to nucypher's staking escrow contract, locking it for
the commitment period.

.. code:: bash


    (nucypher)$ nucypher stake create

        Account
    --  ------------------------------------------
     0  0x63e478bc474eBb6c31568ff131cCd95C24bfD552
     1  0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
     2  0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE
    Select index of staking account [0]: 1
    Selected 1: 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
    Enter stake value in NU (15000 NU - 30000 NU) [30000]: 30000
    Enter stake duration (30 - 47103) [365]: 30

    ══════════════════════════════ STAGED STAKE ══════════════════════════════

    Staking address: 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
    ~ Chain      -> ID # <CHAIN_ID>
    ~ Value      -> 30000 NU (30000000000000000000000 NuNits)
    ~ Duration   -> 30 Days (30 Periods)
    ~ Enactment  -> Jun 19 20:00 EDT (period #18433)
    ~ Expiration -> Jul 19 20:00 EDT (period #18463)

    ═════════════════════════════════════════════════════════════════════════

    * Ursula Node Operator Notice *
    -------------------------------

    By agreeing to stake 30000 NU (30000000000000000000000 NuNits):

    - Staked tokens will be locked for the stake duration.

    - You are obligated to maintain a networked and available Ursula-Worker node
      bonded to the staker address 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f for the duration
      of the stake(s) (30 periods).

    - Agree to allow NuCypher network users to carry out uninterrupted re-encryption
      work orders at-will without interference.

    Failure to keep your node online, or violation of re-encryption work orders
    will result in the loss of staked tokens as described in the NuCypher slashing protocol.

    Keeping your Ursula node online during the staking period and successfully
    producing correct re-encryption work orders will result in rewards
    paid out in ethers retro-actively and on-demand.

    Accept ursula node operator obligation? [y/N]: y
    Publish staged stake to the blockchain? [y/N]: y


You will need to confirm two transactions here.


5. List existing stakes
~~~~~~~~~~~~~~~~~~~~~~~

Once you have created one or more stakes, you can view all active stake for connected wallets:

.. code:: bash

    (nucypher)$ nucypher stake list

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f ════
    Worker NO_WORKER_BONDED ════
    --------------  -----------------------------------
    Status          Never Made a Commitment (New Stake)
    Restaking       Yes (Unlocked)
    Winding Down    No
    Unclaimed Fees  0 ETH
    Min fee rate    0 ETH
    --------------  -----------------------------------
    ╒═══════╤══════════╤═════════════╤═════════════╤═══════════════╕
    │   Idx │ Value    │   Remaining │ Enactment   │ Termination   │
    ╞═══════╪══════════╪═════════════╪═════════════╪═══════════════╡
    │ 	0   │ 30000 NU │      	  31 │ Jun 19 2020 │ Jul 19 2020   │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╛

If the Worker in the list is shown as ``NO_WORKER_BONDED``, it means that you haven't yet
bonded a Worker node to your Staker.


.. note:: Stakers accounts without a worker bonded will be highlighted in red.


.. _bond-worker:

6. Bond a Worker
~~~~~~~~~~~~~~~~~

After initiating a stake, the staker must delegate access to a work address through *bonding*.
There is a 1:1 relationship between the roles: A Staker may have multiple Stakes but only ever has one Worker at a time.

.. important:: The Worker cannot be changed for a minimum of 2 periods (48 Hours) once bonded.

.. code:: bash

    (nucypher)$ nucypher stake bond-worker

            Account
    --  ------------------------------------------
     0  0x63e478bc474eBb6c31568ff131cCd95C24bfD552
     1  0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
     2  0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE
    Select index of staking account [0]: 1
    Selected 1: 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
    Enter worker address: 0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE
    Commit to bonding worker 0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE to staker 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f for a minimum of 2 periods? [y/N]: y

.. note::

    The worker's address must be EIP-55 checksum valid, however, geth shows addresses in the lowercase
    normalized format.  You can convert the normalized address to checksum format on etherscan or using the geth console:

    .. code:: bash

        $ geth attach ~/.ethereum/geth.ipc
        > eth.accounts
        ["0x63e478bc474ebb6c31568ff131ccd95c24bfd552", "0x270b3f8af5ba2b79ea3bd6a6efc7ecab056d3e3f", "0x45d33d1ff0a7e696556f36de697e5c92c2cccfae"]
        > web3.toChecksumAddress(eth.accounts[2])
        "0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE"


After this step, you're finished with the Staker, and you can proceed to :ref:`ursula-config-guide`.
