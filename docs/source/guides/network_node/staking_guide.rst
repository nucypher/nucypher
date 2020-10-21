.. _staking-guide:

==========================
Staker Configuration Guide
==========================

NuCypher staking operations are divided into two roles "Staker" and "Worker" - This Guide is for Stakers.

Staker Overview
----------------

*Staker* - Controls NU tokens, manages staking, and collects rewards.

The Staker is a manager of one or more stakes, delegating active network participation to a *Worker* through *bonding*.
There is a 1:1 relationship between the roles: A Staker controls a single ethereum account and may have multiple Stakes,
but only ever has one Worker. A fully synced ethereum node is required - The staker's account needs NU tokens to stake
as well as enough ether to pay for transaction gas. Stakers can run on a laptop and do not need to remain online since
they only need to perform stake management transactions. Using a hardware wallet is *highly* recommended, they are ideal
for stakers since only temporarily access to private keys is required during stake management while providing a higher standard
of security than software wallets.

Mainnet Staking Procedure:

#. Install ``nucypher`` on Staker's machine (see :doc:`/guides/installation_guide`)
#. Obtain a Stake with tokens (initially via :ref:`WorkLock <worklock-guide>` at launch)
#. Initialize a new StakeHolder (see `Initialize a new stakeholder`_)
#. Bond a Worker to your Staker using the worker's ethereum address (see `Bonding a Worker`_)

.. note::

    For testnets the typical staking procedure is:

        #. Install ``nucypher`` on Staker's machine (see :doc:`/guides/installation_guide`)
        #. Establish ethereum account, provider, and, optionally, signer (see `Staking`_)
        #. Request testnet tokens by joining the `Discord server <https://discord.gg/7rmXa3S>`_ and type ``.getfunded <YOUR_STAKER_ETH_ADDRESS>`` in the #testnet-faucet channel
        #. Initialize a new StakeHolder and Stake (see `Initialize a new stakeholder`_)
        #. Initialize a new stake (see `Initialize a new stake`_)
        #. Bond a Worker to a Staker using the worker's ethereum address (see `Bonding a Worker`_)


Staking CLI
------------

All staking-related operations done by Staker are performed through the ``nucypher stake`` command:

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
| ``--hw-wallet`` | Use a hardware wallet                      |
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

Running an Ethereum Node for Staking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Staking transactions can be broadcasted using either a local or remote ethereum node. See
:ref:`using-eth-node` for more information.


Using External Signing
**********************

By default, transaction signing requests are forwarded to the configured ethereum provider. This is the typical
configuration for locally or independently run ethereum nodes. To use a remote ethereum provider
(e.g. Alchemy, Infura, Public Remote Node) an external transaction signing client (e.g. `clef` or `geth`) is needed
separate from the broadcasting node.

Using Clef
++++++++++
See :ref:`signing-with-clef` for setting up Clef. By default, all requests to the clef signer require manual
confirmation. This includes not only transactions but also more innocuous requests such as listing the accounts
that the signer is handling. This means, for example, that a command like ``nucypher stake accounts`` will first ask
for user confirmation in the clef CLI before showing the staker accounts. You can automate this confirmation by
using :ref:`clef-rules`.


Using Clef with nucypher commands
+++++++++++++++++++++++++++++++++

.. code:: bash

    $ nucypher <COMMAND> <ACTION> --signer <CLEF IPC PATH> --hw-wallet

Some examples:

.. code:: bash

    # Create a new stakeholder with clef as the default signer
    $ nucypher stake init-stakeholder --signer clef:///home/<username>/.clef/clef.ipc ...

    # Update an existing configuration with clef as the default signer
    $ nucypher stake config --signer clef:///home/<username>/.clef/clef.ipc  # Set clef as the default signer

    # Create a new stake using inline signer and provider values
    $ nucypher stake create --signer clef:///home/<username>/.clef/clef.ipc --provider ~/.ethereum/geth.ipc


Initialize a new stakeholder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before continuing with stake initiation and management, A setup step is required to configure nucypher for staking.
This will create a configuration file (`~/.local/share/nucypher/stakeholder.json`) containing editable configuration values.

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --signer <SIGNER URI> --provider <PROVIDER> --network <NETWORK_NAME>

where:

    * If you utilized :ref:`signing-with-clef`, the ``SIGNER URI`` is ``clef:///home/<username>/.clef/clef.ipc``
      (on MacOS, ``ipc:///Users/<username>/Library/Signer/clef.ipc``)
    * If you ran ``geth`` node as above, your ``<PROVIDER>`` is ``ipc:///home/<username>/.ethereum/geth.ipc``
      (on MacOS, ``ipc:///Users/<username>/Library/Ethereum/geth.ipc``)
    * ``<NETWORK_NAME>`` is the name of the NuCypher network domain where the staker will participate.


.. note:: If you are using NuCypher's testnet, this name is ``ibex``.


Initialize a new stake
~~~~~~~~~~~~~~~~~~~~~~

Once you have configured nucypher for staking, you can proceed with stake initiation.
This operation will transfer an amount of tokens to nucypher's staking escrow contract and lock them for
the commitment period.

.. note:: Use ``--hw-wallet`` if you are using a hardware wallet or clef to prevent password prompts.

.. code:: bash


    (nucypher)$ nucypher stake create --hw-wallet

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

    (nucypher)$ nucypher stake bond-worker --hw-wallet

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
          You can convert the normalized address to checksum format in geth console:

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
until a future period (``release_period``). Once enabled, the `StakingEscrow` contract will not
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

Wind down is *disabled* by default. To start winding down an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake winddown --hw-wallet


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

Merging or editing sub-stakes can lead to 'unused', inactive sub-stakes remaining on-chain. 
These unused sub-stakes add unnecessary gas costs to daily operations.
To remove unused sub-stake:

.. code:: bash

    (nucypher)$ nucypher stake remove-unused --hw-wallet


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

Staking using a preallocation contract
---------------------------------------

Each NuCypher staker with a preallocation will have some amount of tokens locked
in a preallocation contract named ``PreallocationEscrow``, which is used to stake and
perform other staker-related operations.
From the perspective of the main NuCypher contracts, each ``PreallocationEscrow``
contract represents a staker, no different from "regular" stakers.
However, from the perspective of the preallocation user, things are different
since the contract can't perform transactions, and it's the preallocation user
(also known as the "`beneficiary`" of the contract)
who has to perform staking operations.

As part of the preallocation process, beneficiaries receive an allocation file,
containing the ETH addresses of their beneficiary account and corresponding
preallocation contract.

In general, preallocation users can use all staking-related operations offered
by the CLI in the same way as described above, except that they have to specify
the path to the allocation file using the option ``--allocation-filepath PATH``.

For example, to create a stake:

.. code:: bash

    (nucypher)$ nucypher stake create --hw-wallet --allocation-filepath PATH


Or to bond a worker:

.. code:: bash

    (nucypher)$ nucypher stake bond-worker --hw-wallet --allocation-filepath PATH


As an alternative to the ``--allocation-filepath`` flag, preallocation users
can directly specify their beneficiary and staking contract addresses with the
``--beneficiary-address ADDRESS`` and ``--staking-address ADDRESS``, respectively.

Finally, note that collected staking rewards are always placed in the original
staking account, which for preallocation users is the staking contract.
Run the following command to view the balance of the ``PreallocationEscrow`` contract:

.. code:: bash

    (nucypher)$ nucypher stake preallocation --status --allocation-filepath PATH

    -------------------------- Addresses ---------------------------
    Staking contract: ... 0x0f4Ebe8a28a8eF33bEcD6A3782D74308FC35D021
    Beneficiary: ........ 0x4f5e87f833faF9a747463f7E4387a0d9323a3979

    ------------------------ Locked Tokens -------------------------
    Initial locked amount: 35000 NU
    Current locked amount: 35000 NU
    Locked until: ........ 2020-12-31 16:33:37+00:00

    ---------------------- NU and ETH Balance ----------------------
    NU balance: .......... 17.345 NU
        Available: ....... 12.345 NU
    ETH balance: ......... 0 ETH


To withdraw the unlocked tokens, you need to retrieve them from the
``PreallocationEscrow`` contract using the following command:

.. code:: bash

    (nucypher)$ nucypher stake preallocation --withdraw-tokens --allocation-filepath PATH


.. note:: If you're a preallocation user, recall that you're using a contract to stake.
  Replace ``<YOUR STAKER ADDRESS>`` with the contract address when configuring your node.
  If you don't know this address, you'll find it in the preallocation file.


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


Stake 30000 NU for 90 Periods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake init --value 30000 --duration 90 --hw-wallet
    ...


Divide stake at index 0, at 15000 NU for 30 additional Periods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake divide --index 0 --value 15000 --duration 30 --hw-wallet
    ...

Worker configuration
------------------------

See :ref:`ursula-config-guide`.
