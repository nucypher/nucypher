.. _staking-guide:

==========================
Staker Configuration Guide
==========================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Stakers.

Staker Overview
----------------

*Staker* - Controls NU tokens, manages staking, and collects rewards.

The Staker is a manager of one or more NU stakes.  A stake is initiated by locking NU into the *"Staking Escrow "*
contract for a fixed duration of time.  Staked NU earns two income streams: inflation rewards (NU) and policy fees (ETH).
Staked NU unlocks with each period of completed, depending on *re-stake* and *wind-down* (more on this later).

Active network participation (work) is delegated to a *Worker* node through *bonding*. There is a 1:1 relationship
between the roles; One staker to one worker. A Staker controls a single ethereum account and may have multiple stakes,
but only ever has one Worker bonded at a time. Once the stake is bonded to a worker node, it can only
be *rebonded* once every 2 periods (48 Hours).

The staking CLI itself is lightweight and can be run on commodity hardware. While there are no
specific minimum system constraints, there are some basic requirements for stakers:

#. Hosted or Remote Ethereum Node (Infura, Geth, etc.)
#. Hardware or Software Wallet (Trezor, Ledger, Keyfile)
#. At least 15,000 NU
#. Small amount of ether to pay for transaction gas

Using a hardware wallet is *highly* recommended. They are ideal for stakers since they hold NU and
only temporary access to private keys is required during stake management while providing a higher standard
of security than software wallets or keyfiles.

Mainnet Staking Procedure:

#. Obtain and Secure NU (initially via :ref:`WorkLock <worklock-guide>` at launch)
#. Install ``nucypher`` on Staker's system (see :doc:`/guides/installation_guide`)
#. Configure nucypher CLI for staking (see `Initialize a new stakeholder`_)
#. Bond a Worker to your Staker using the worker's ethereum address (see `Bonding a Worker`_)

.. note::

    If you are running a testnet node, Testnet tokens can be obtained by joining the
    `Discord server <https://discord.gg/7rmXa3S>`_ and typing ``.getfunded <YOUR_STAKER_ETH_ADDRESS>``
    in the #testnet-faucet channel.


Staking CLI
------------

All staking-related operations can be executed through the ``nucypher stake`` command:

.. code:: bash

    (nucypher)$ nucypher stake ACTION [OPTIONS]


**Stake Command Actions**

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``init-stakeholder``| Create a new stakeholder configuration                                        |
+----------------------+-------------------------------------------------------------------------------+
|  ``create``          | Initialize NuCypher stakes (used with ``--value`` and ``--duration``)         |
+----------------------+-------------------------------------------------------------------------------+
|  ``increase``        | Increase an existing stake's value                                            |
+----------------------+-------------------------------------------------------------------------------+
|  ``list``            | List active stakes for current stakeholder                                    |
+----------------------+-------------------------------------------------------------------------------+
|  ``accounts``        | Show ETH and NU balances for stakeholder's accounts                           |
+----------------------+-------------------------------------------------------------------------------+
|  ``bond-worker``     | Bond a worker to a staker                                                     |
+----------------------+-------------------------------------------------------------------------------+
|  ``unbond-worker``   | Unbond worker currently bonded to a staker                                    |
+----------------------+-------------------------------------------------------------------------------+
|  ``collect-reward``  | Withdraw staking compensation from the contract to your wallet                |
+----------------------+-------------------------------------------------------------------------------+
|  ``divide``          | Create a new stake from part of an existing one                               |
+----------------------+-------------------------------------------------------------------------------+
|  ``restake``         | Manage automatic reward re-staking                                            |
+----------------------+-------------------------------------------------------------------------------+
|  ``prolong``         | Prolong an existing stake's duration                                          |
+----------------------+-------------------------------------------------------------------------------+
|  ``winddown``        | Manage winding down of stakes                                                 |
+----------------------+-------------------------------------------------------------------------------+
|  ``snapshots``       | Manage taking snapshots                                                       |
+----------------------+-------------------------------------------------------------------------------+
|  ``mint``            | Mint last portion of reward                                                   |
+----------------------+-------------------------------------------------------------------------------+
|  ``merge``           | Merge two stakes into one                                                     |
+----------------------+-------------------------------------------------------------------------------+
|  ``remove-unused``   | Remove unused stake                                                           |
+----------------------+-------------------------------------------------------------------------------+

**Stake Command Options**

+-----------------+--------------------------------------------+
| Option          |  Description                               |
+=================+============================================+
|  ``--value``    | Stake value                                |
+-----------------+--------------------------------------------+
|  ``--duration`` | Stake duration of extension                |
+-----------------+--------------------------------------------+
|  ``--index``    | Stake index                                |
+-----------------+--------------------------------------------+

**Re-stake Command Options**

+-------------------------+---------------------------------------------+
| Option                  |  Description                                |
+=========================+=============================================+
|  ``--enable``           | Enable re-staking                           |
+-------------------------+---------------------------------------------+
|  ``--disable``          | Disable re-staking                          |
+-------------------------+---------------------------------------------+
|  ``--lock-until``       | Enable re-staking lock until release period |
+-------------------------+---------------------------------------------+


Staking
--------

Establish an ethereum provider
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Staking transactions can be broadcasted using either a local or remote ethereum node. See
:ref:`using-eth-node` for more information.

.. note::

    for local geth node operators the default location of geth's IPC file
    is ``/home/<username>/.ethereum/geth.ipc``  (on MacOS, ``ipc:///Users/<username>/Library/Ethereum/geth.ipc``)


Choosing a Transaction Singer
*****************************

By default, all transaction and message signing requests are forwarded to the configured ethereum provider.
To use a remote ethereum provider (e.g. Infura, Alchemy, Another Remote Node) a local transaction signer must
be configured in addition to the broadcasting node.  This can be a hardware wallet, software wallet, or clef.

.. note::

    Currently Only trezor hardware wallets are supported by the CLI directly.  Ledger functionality can be achieved
    through clef.

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer <SIGNER_URI>

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


Initialize a new stakeholder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before continuing with stake initiation, A setup step is required to configure nucypher for staking.
This will create a JSON configuration file (`~/.local/share/nucypher/stakeholder.json`) containing editable
configuration values.  No new keys or secrets are created in this step it's just for configuration.

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --signer <SIGNER URI> --provider <PROVIDER>

.. note:: If you are using NuCypher's Rinkeby testnet, passing the network name is rquired ``--network ibex``.


Initialize a new stake
~~~~~~~~~~~~~~~~~~~~~~

Once you have configured nucypher for staking, you can proceed with stake initiation.
This operation will transfer NU to nucypher's staking escrow contract, locking for
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


If you used a hardware wallet, you will need to confirm two transactions here.


List existing stakes
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
bonded a Worker node to your Staker, so you still have to do it!

.. _bond-worker:

Bonding a Worker
~~~~~~~~~~~~~~~~~~

After initiating a stake, the staker must delegate access to a work address through *bonding*.
There is a 1:1 relationship between the roles: A Staker may have multiple Stakes but only ever has one Worker at a time.

.. note:: The Worker cannot be changed for a minimum of 2 periods once bonded.

.. note:: Stakers without a worker bonded will be highlighted in red.

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


.. note:: The worker's address must be EIP-55 checksum valid, however, geth shows addresses in the normalized format.
          You can convert the normalized address to checksum format on etherscan or using the geth console:

.. code:: bash

    $ geth attach ~/.ethereum/geth.ipc
    > eth.accounts
    ["0x63e478bc474ebb6c31568ff131ccd95c24bfd552", "0x270b3f8af5ba2b79ea3bd6a6efc7ecab056d3e3f", "0x45d33d1ff0a7e696556f36de697e5c92c2cccfae"]
    > web3.toChecksumAddress(eth.accounts[2])
    "0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE"


After this step, you're finished with the Staker, and you can proceed to :ref:`ursula-config-guide`.


Modifying Active Stakes
~~~~~~~~~~~~~~~~~~~~~~~~

Several administrative operations can be performed on active stakes:

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``restake``         | Manage automatic reward re-staking                                            |
+----------------------+-------------------------------------------------------------------------------+
|  ``prolong``         | Prolong an existing stake's duration                                          |
+----------------------+-------------------------------------------------------------------------------+
|  ``winddown``        | Manage winding down of stakes                                                 |
+----------------------+-------------------------------------------------------------------------------+
|  ``divide``          | Create a new stake from part of an existing one                               |
+----------------------+-------------------------------------------------------------------------------+
|  ``increase``        | Increase an existing stake's value                                            |
+----------------------+-------------------------------------------------------------------------------+


Manage automatic reward re-staking
**********************************

As your Ursula performs work, all rewards are automatically added to your existing stake to optimize earnings.
This feature, called `re-staking`, is *enabled* by default.

To disable re-staking:

.. code:: bash

    (nucypher)$ nucypher stake restake --disable

To enable re-staking again:

.. code:: bash

    (nucypher)$ nucypher stake restake --enable


Additionally, you can enable **re-stake locking**, an on-chain commitment to continue re-staking
until a future period. Once enabled, the ``StakingEscrow`` contract will not
allow **re-staking** to be disabled until the release period begins, even if you are the stake owner.

.. code:: bash

    (nucypher)$ nucypher stake restake --lock-until 12345

No action is needed to release the re-staking lock once the release period begins.


.. _staking-prolong:

Prolong
*******

Existing stakes can be extended by a number of periods as long as the resulting
stake's duration is not shorter than the minimum. To prolong an existing stake's duration:

.. code:: bash

    (nucypher)$ nucypher stake prolong --hw-wallet


Wind Down
**********

The proportion of staking rewards received by a staker depends on the
stake size and the remaining locked duration.

When wind down is enabled, the locked duration decreases after each period which results
in reduced staking yield. When disabled, the stake's locked duration remains
constant and improves staking yield.
See :ref:`sub-stake-winddown` for more information.

Wind down is *disabled* by default.

.. note:: WorkLock participants have wind down *enabled* by default.

To start winding down an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake winddown --enable


To stop winding down:

.. code:: bash

    (nucypher)$ nucypher stake winddown --disable


Snapshots
*********

Taking snapshots is *enabled* by default. Snapshots must be enabled to participate in the DAO, but it has a slight cost in gas every time your staking balance changes. To stop taking snapshots:

.. code:: bash

    (nucypher)$ nucypher stake snapshots --disable
	
To enable snapshots again:

.. code:: bash

    (nucypher)$ nucypher stake snapshots --enable



Divide
******

Existing stakes can be divided into smaller :ref:`sub-stakes <sub-stakes>`, with different values and durations. Dividing a stake
allows stakers to accommodate different liquidity needs since sub-stakes can have different durations. Therefore, a
staker can liquidate a portion of their overall stake at an earlier time.

To divide an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake divide --hw-wallet

    Select Stake: 0
    Enter target value (15000 NU - 16437.841006996376688377 NU): 15000
    Enter number of periods to extend: 20

    ══════════════════════════════ ORIGINAL STAKE ════════════════════════════

    Staking address: 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
    ~ Original Stake: | - | 0x270b | 0x45D3 | 0 | 31437.841006996376688377 NU | 33 periods . | Jun 19 20:00 EDT - Jul 22 20:00 EDT


    ══════════════════════════════ STAGED STAKE ══════════════════════════════

    Staking address: 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f
    ~ Chain      -> ID # 4 | Rinkeby
    ~ Value      -> 15000 NU (15000000000000000000000 NuNits)
    ~ Duration   -> 53 Days (53 Periods)
    ~ Enactment  -> Jun 19 20:00 EDT (period #18433)
    ~ Expiration -> Aug 11 20:00 EDT (period #18486)

    ═════════════════════════════════════════════════════════════════════════
    Publish stake division to the blockchain? [y/N]: y
    Enter password to unlock account 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f:
    Confirm transaction DIVIDESTAKE on hardware wallet... (76058 gwei @ 1000000000)
    Broadcasting DIVIDESTAKE Transaction (76058 gwei @ 1000000000)...
    Successfully divided stake
    OK | 0x74ddd647de6eaca7ef0c485706ef526001d959a3c2eaa98699e087a7d259d08b (75349 gas)
    Block #6711982 | 0xd1c6d6df257ecd05632550565edb709ae577066a60ca433bc4d23de5fb332009
     See https://rinkeby.etherscan.io/tx/0x74ddd647de6eaca7ef0c485706ef526001d959a3c2eaa98699e087a7d259d08b


    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f ════
    Worker 0x45D33d1Ff0A7E696556f36DE697E5C92C2CCcFaE ════
    --------------  ----------------
    Status          Committed #18436
    Restaking       Yes (Unlocked)
    Winding Down    No
    Unclaimed Fees  0 ETH
    Min fee rate    0 ETH
    --------------  ----------------
    ╒═══════╤═════════════════════════════╤═════════════╤═════════════╤═══════════════╕
    │   Idx │ Value                   	  │   Remaining │ Enactment   │ Termination   │
    ╞═══════╪═════════════════════════════╪═════════════╪═════════════╪═══════════════╡
    │ 	0   │ 16437.841006996376688377 NU │         31  │ Jun 19 2020 │ Jul 22 2020   │
    ├───────┼─────────────────────────────┼─────────────┼─────────────┼───────────────┤
    │ 	1   │ 15000 NU                	  │         51  │ Jun 19 2020 │ Aug 11 2020   │
    ╘═══════╧═════════════════════════════╧═════════════╧═════════════╧═══════════════╛


Increase
********

Existing stakes can be increased by an amount of NU as long as the resulting
staker's locked value is not greater than the maximum. To increase an existing stake's value:

.. code:: bash

    (nucypher)$ nucypher stake increase --hw-wallet


Merge
*****

Two stakes with the same final period can be merged into one stake. 
This can help to decrease gas consumption in some operations. To merge two stakes:

.. code:: bash

    (nucypher)$ nucypher stake merge --hw-wallet


Remove unused sub-stake
***********************

When sub-stakes terminate, are merged or edited,
there may be 'unused', inactive sub-stakes remaining on-chain.
Continued tracking of these unused sub-stakes adds unnecessary gas costs to daily operations.
Consequently, removal of unused sub-stakes will reduce daily gas costs.

Unused sub-stakes can be displayed by listing all sub-stakes
and will be indicated by the ``INACTIVE`` status label.

.. code:: bash

    (nucypher)$ nucypher stake list --all --hw-wallet

    ...

    ╒═══════╤═══════════════╤═════════════╤═════════════╤═══════════════╤═══════════╕
    │   Idx │ Value         │   Remaining │ Enactment   │ Termination   │ Status    │
    ╞═══════╪═══════════════╪═════════════╪═════════════╪═══════════════╪═══════════╡
    │     0 │ 123456.789 NU │          -4 │ Oct 15 2020 │ Nov 19 2020   │ INACTIVE  │
    ├───────┼───────────────┼─────────────┼─────────────┼───────────────┼───────────┤
    │     1 │ 123456.789 NU │          27 │ Oct 15 2020 │ Dec 20 2020   │ DIVISIBLE │
    ├───────┼───────────────┼─────────────┼─────────────┼───────────────┼───────────┤


To remove an unused sub-stake, run the following command and select the index
of your ``INACTIVE`` sub-stake:

.. code:: bash

    (nucypher)$ nucypher stake remove-unused --hw-wallet


In order to make the operation as simple and cheap as possible,
the removal algorithm simply relocates the last active sub-stake to the slot
occupied by the currently inactive one, so you will notice a slight
re-ordering of your sub-stakes. This is normal and doesn't have any negative implications.


Collect rewards earned by the staker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NuCypher nodes earn two types of rewards: staking rewards (in NU) and policy fees (i.e., service fees in ETH).
To collect these rewards use ``nucypher stake collect-reward`` with flags ``--staking-reward`` and ``--policy-fee``
(or even both).

While staking rewards can only be collected to the original staker account, you can decide which account receives
policy fees using the ``--withdraw-address <ETH_ADDRESS>`` flag.

.. code:: bash

    (nucypher)$ nucypher stake collect-reward --staking-reward --policy-fee --staking-address 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f --hw-wallet
    Collecting 228.340621510864128225 NU from staking rewards...
    Confirm transaction WITHDRAW on hardware wallet... (500000 gwei @ 1000000000)
    Broadcasting WITHDRAW Transaction (500000 gwei @ 1000000000)...
    OK | 0x1c59af9353b016080fef9e93ddd03fde4260b6c282880db7b15fc0d4f28b2d34 (124491 gas)
    Block #6728952 | 0xdadfef1767eb5bdc4bb4ad469a5f7aded44a87799dd2ee0edd6b6147951dbd3f
     See https://rinkeby.etherscan.io/tx/0x1c59af9353b016080fef9e93ddd03fde4260b6c282880db7b15fc0d4f28b2d34

    Collecting 1.0004E-13 ETH from policy fees...
    Confirm transaction WITHDRAW on hardware wallet... (42070 gwei @ 1000000000)
    Broadcasting WITHDRAW Transaction (42070 gwei @ 1000000000)...
    OK | 0xba2afb864c24d783c5185429706c77a39e9053570de892a351dd86f7719fe58b (41656 gas)
    Block #6728953 | 0x1238f61e8adf8bf42e022f5182b692aca5ec5bf45c70871156ca540055daaa94
     See https://rinkeby.etherscan.io/tx/0xba2afb864c24d783c5185429706c77a39e9053570de892a351dd86f7719fe58b

You can run ``nucypher stake accounts`` to verify that your staking compensation
is indeed in your wallet. Use your favorite Ethereum wallet (MyCrypto or Metamask
are suitable) to transfer out the compensation earned (NU tokens or ETH) after
that.

Note that you will need to confirm two transactions if you collect both types of
staking compensation if you use a hardware wallet.

.. note:: If you want to withdraw all tokens when all of them are unlocked - 
          make sure to call ``nucypher stake mint`` first to ensure the last reward is included


One-Liners
--------------

Additional command line flags are available for one-line operation:

+--------------------+----------------+--------------+
| Option             | Flag           | Description  |
+====================+================+==============+
| ``stake value``    | ``--value``    | in NU        |
+--------------------+----------------+--------------+
| ``stake duration`` | ``--duration`` | in periods   |
+--------------------+----------------+--------------+
| ``stake index``    | ``--index``    | to divide    |
+--------------------+----------------+--------------+


Stake 30000 NU for 90 Periods:

.. code:: bash

    (nucypher)$ nucypher stake create --value 30000 --duration 90
    ...


Divide stake at index 0, at 15000 NU for 30 additional Periods:

.. code:: bash

    (nucypher)$ nucypher stake divide --index 0 --value 15000 --duration 30
    ...


Worker configuration
------------------------

See :ref:`ursula-config-guide`.
