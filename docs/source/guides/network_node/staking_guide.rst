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

Staking Procedure:

1) Install ``nucypher`` on Staking machine (see :doc:`/guides/installation_guide`)
2) Run an ethereum node on the Staker's machine eg. geth, parity, etc. (see `Run an Ethereum node for Staking`_)
3) Create staker's ethereum address (see `Run an Ethereum node for Staking`_)
4) Request testnet tokens by joining the `Discord server <https://discord.gg/7rmXa3S>`_ and type ``.getfunded <YOUR_STAKER_ETH_ADDRESS>`` in the #testnet-faucet channel
5) Initiate a new StakeHolder and Stake (see `Initialize a new stakeholder`_)
6) Create and fund worker's ethereum address with ETH
7) Bond a Worker to a Staker using the worker's ethereum address (see `Bonding a Worker`_)
8) Optionally, modify stake settings (see `Modifying Active Stakes`_)
9) Configure and Run a Worker Node (see :ref:`ursula-config-guide`)


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
|  ``list``            | List active stakes for current stakeholder                                    |
+----------------------+-------------------------------------------------------------------------------+
|  ``accounts``        | Show ETH and NU balances for stakeholder's accounts                           |
+----------------------+-------------------------------------------------------------------------------+
|  ``sync``            | Synchronize stake data with on-chain information                              |
+----------------------+-------------------------------------------------------------------------------+
|  ``set-worker``      | Bond a worker to a staker                                                     |
+----------------------+-------------------------------------------------------------------------------+
|  ``detach-worker``   | Detach worker currently bonded to a staker                                    |
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


Run an Ethereum node for Staking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assuming you have ``geth`` installed, let's run a node on the Görli testnet.

.. code:: bash

    $ geth --goerli

If you want to use your hardware wallet, just connect it to your machine. You'll see something like this in logs:

.. code:: bash

    INFO [08-30|15:50:39.153] New wallet appeared      url=ledger://0001:000b:00      status="Ethereum app v1.2.7 online"

If you see something like ``New wallet appeared, failed to open`` in the logs,
you need to reconnect the hardware wallet (without turning the ``geth`` node
off).

If you don't have a hardware wallet, you can create a software one:

Whilst running the initialized node:

.. code:: bash

    Linux:
    $ geth attach /home/<username>/.ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts
    ["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]

    MacOS:
    $ geth attach /Users/<username>/Library/Ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts
    ["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]

Where ``0x287a817426dd1ae78ea23e9918e2273b6733a43d`` is your newly created
account address and ``<username>`` is your user.


Initialize a new stakeholder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Before continuing with stake initiation and management, A setup step is required to configure nucypher for staking.
This will create a configuration file (`~/.local/share/nucypher/stakeholder.josn`) containing editable configuration values.

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --provider <PROVIDER> --network <NETWORK_NAME>

If you ran ``geth`` node as above, your ``<PROVIDER>`` is
``ipc:///home/<username>/.ethereum/goerli/geth.ipc``
(on MacOS, ``ipc:///Users/<username>/Library/Ethereum/goerli/geth.ipc``)

``<NETWORK_NAME>`` is the name of the NuCypher network domain where the staker will participate.

.. note:: If you're participating in NuCypher's incentivized testnet, this name is ``cassandra``.


Initialize a new stake
~~~~~~~~~~~~~~~~~~~~~~~~

Once you have configured nucypher for staking, you can proceed with stake initiation.
This operation will transfer an amount of tokens to nucypher's staking escrow contract and lock them for
the commitment period.

.. note:: Use ``--hw-wallet`` if you are using a hardware wallet to prevent password prompts.

.. code:: bash

    (nucypher)$ nucypher stake create --hw-wallet

    Select staking account [0]: 0
    Enter stake value in NU [15000]: 15000
    Enter stake duration (30 periods minimum): 30

    ============================== STAGED STAKE ==============================

    Staking address: 0xbb01c4fE50f91eF73c5dD6eD89f38D55A6b1EdCA
    ~ Chain      -> ID # 5 | Goerli
    ~ Value      -> 15000 NU (1.50E+22 NuNits)
    ~ Duration   -> 30 Days (30 Periods)
    ~ Enactment  -> 2019-08-19 09:51:16.704875+00:00 (period #18127)
    ~ Expiration -> 2019-09-18 09:51:16.705113+00:00 (period #18157)

    =========================================================================

    * Ursula Node Operator Notice *
    -------------------------------

    By agreeing to stake 15000 NU (15000000000000000000000 NuNits):

    - Staked tokens will be locked for the stake duration.

    - You are obligated to maintain a networked and available Ursula-Worker node
      bonded to the staker address 0xbb01c4fE50f91eF73c5dD6eD89f38D55A6b1EdCA for the duration
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

    Stake initialization transaction was successful.

    Transaction details:
    OK | deposit stake | 0xe05babab52d00157d0c6e95b7c5165a95adc0ee7ff64ca4d89807805f0ef0fcf (229181 gas)
    Block #16 | 0xbf8252bc84831c26fc91a2272047e394ec0356af515d785d4a179596e722d836

    StakingEscrow address: 0xDe09E74d4888Bc4e65F589e8c13Bce9F71DdF4c7

If you used a hardware wallet, you will need to confirm two transactions here.


List existing stakes
~~~~~~~~~~~~~~~~~~~~~~~

Once you have created one or more stakes, you can view all active stake for connected wallets:

.. code:: bash

    (nucypher)$ nucypher stake list

    ======================================= Active Stakes =========================================

    | ~ | Staker | Worker | # | Value    | Duration     | Enactment
    |   | ------ | ------ | - | -------- | ------------ | -----------------------------------------
    | 0 | 0xbb01 | 0xdead | 0 | 15000 NU | 41 periods . | Aug 04 12:15:16 CEST - Sep 13 12:15:16 CEST
    | 1 | 0xbb02 | 0xbeef | 1 | 15000 NU | 30 periods . | Aug 20 12:15:16 CEST - Sep 18 12:15:16 CEST
    | 2 | 0xbb03 | 0x0000 | 0 | 30000 NU | 30 periods . | Aug 09 12:15:16 CEST - Sep 9 12:15:16 CEST

If the Worker in the list is shown as ``0x0000``, it means that you haven't yet
attached a Worker node to your Staker, so you still have to do it!

.. _bond-worker:

Bonding a Worker
~~~~~~~~~~~~~~~~~~

After initiating a stake, the staker must delegate access to a work address through *bonding*.
There is a 1:1 relationship between the roles: A Staker may have multiple Stakes but only ever has one Worker at a time.

.. note:: The Worker cannot be changed for a minimum of 2 periods once set.

.. note:: Stakers without a worker bonded will be highlighted in yellow (sometimes called "Detached" or "Headless").

.. code:: bash

    (nucypher)$ nucypher stake set-worker --hw-wallet

    ======================================= Active Stakes =========================================

    | ~ | Staker | Worker | # | Value    | Duration     | Enactment
    |   | ------ | ------ | - | -------- | ------------ | -----------------------------------------
    | 0 | 0xbb01 | 0xdead | 0 | 15000 NU | 41 periods . | Aug 04 12:15:16 CEST - Sep 13 12:15:16 CEST
    | 1 | 0xbb02 | 0xbeef | 1 | 15000 NU | 30 periods . | Aug 20 12:15:16 CEST - Sep 18 12:15:16 CEST
    | 2 | 0xbb03 | 0x0000 | 0 | 30000 NU | 30 periods . | Aug 09 12:15:16 CEST - Sep 9 12:15:16 CEST

    Select Stake: 2
    Enter Worker Address: 0xbeefc4fE50f91eF73c5dD6eD89f38D55A6b1EdCA
    Worker 0xbb04c4fE50f91eF73c5dD6eD89f38D55A6b1EdCA successfully bonded to staker 0xbb03...

    OK!

.. note:: The worker's address must be EIP-55 checksum valid, however, geth shows addresses in the normalized format.
          You can convert the normalized address to checksum format in geth console:

.. code:: bash

    $ geth attach ~/.ethereum/goerli/geth.ipc
    > eth.accounts
    ["0x287a817426dd1ae78ea23e9918e2273b6733a43d", "0xc080708026a3a280894365efd51bb64521c45147"]
    > web3.toChecksumAddress(eth.accounts[0])
    "0x287A817426DD1AE78ea23e9918e2273b6733a43D"

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
stake's duration is not longer than the maximum. To prolong an existing stake's duration:

.. code:: bash

    (nucypher)$ nucypher stake prolong --hw-wallet


Wind Down
**********

Wind down is *disabled* by default. To start winding down an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake winddown --hw-wallet


Divide
******

Existing stakes can be divided into smaller :ref:`sub-stakes <sub-stakes>`, with different values and durations. Dividing a stake
allows stakers to accommodate different liquidity needs since sub-stakes can have different durations. Therefore, a
staker can liquidate a portion of their overall stake at an earlier time.

To divide an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake divide --hw-wallet

    Select Stake: 2
    Enter target value (must be less than or equal to 30000 NU): 15000
    Enter number of periods to extend: 1

    ============================== ORIGINAL STAKE ============================

    Staking address: 0xbb0300106378096883ca067B198d9d98112760e7
    ~ Original Stake: | - | 0xbb03 | 0xbb04 | 0 | 30000 NU | 39 periods . | Aug 09 12:29:44 CEST - Sep 16 12:29:44 CEST


    ============================== STAGED STAKE ==============================

    Staking address: 0xbb0300106378096883ca067B198d9d98112760e7
    ~ Chain      -> ID # 5 | Goerli
    ~ Value      -> 15000 NU (1.50E+22 NuNits)
    ~ Duration   -> 39 Days (39 Periods)
    ~ Enactment  -> 2019-08-09 10:29:49.844348+00:00 (period #18117)
    ~ Expiration -> 2019-09-17 10:29:49.844612+00:00 (period #18156)

    =========================================================================
    Is this correct? [y/N]: y
    Enter password to unlock account 0xbb0300106378096883ca067B198d9d98112760e7:

    Successfully divided stake
    OK | 0xfa30927f05967b9a752402db9faecf146c46eda0740bd3d67b9e86dd908b6572 (85128 gas)
    Block #1146153 | 0x2f87bccff86bf48d18f8ab0f54e30236bce6ca5ea9f85f3165c7389f2ea44e45
    See https://goerli.etherscan.io/tx/0xfa30927f05967b9a752402db9faecf146c46eda0740bd3d67b9e86dd908b6572

    ======================================= Active Stakes =========================================

    | ~ | Staker | Worker | # | Value    | Duration     | Enactment
    |   | ------ | ------ | - | -------- | ------------ | -----------------------------------------
    | 0 | 0xbb01 | 0xbb02 | 0 | 15000 NU | 41 periods . | Aug 04 12:29:44 CEST - Sep 13 12:29:44 CEST
    | 1 | 0xbb01 | 0xbb02 | 1 | 15000 NU | 30 periods . | Aug 20 12:29:44 CEST - Sep 18 12:29:44 CEST
    | 2 | 0xbb03 | 0xbb04 | 0 | 15000 NU | 39 periods . | Aug 09 12:30:38 CEST - Sep 16 12:30:38 CEST
    | 3 | 0xbb03 | 0xbb04 | 1 | 15000 NU | 40 periods . | Aug 09 12:30:38 CEST - Sep 17 12:30:38 CEST


Collect rewards earned by the staker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

NuCypher nodes earn two types of rewards: staking rewards (in NU) and policy rewards (i.e., service fees in ETH).
To collect these rewards use ``nucypher stake collect-reward`` with flags ``--staking-reward`` and ``--policy-reward``
(or even both).

While staking rewards can only be collected to the original staker account, you can decide which account receives
policy rewards using the ``--withdraw-address <ETH_ADDRESS>`` flag.

.. code:: bash

    (nucypher)$ nucypher stake collect-reward --staking-reward --policy-reward --staking-address 0x287A817426DD1AE78ea23e9918e2273b6733a43D --hw-wallet

     ____    __            __
    /\  _`\ /\ \__        /\ \
    \ \,\L\_\ \ ,_\    __ \ \ \/'\      __   _ __
     \/_\__ \\ \ \/  /'__`\\ \ , <    /'__`\/\`'__\
       /\ \L\ \ \ \_/\ \L\.\\ \ \\`\ /\  __/\ \ \/
       \ `\____\ \__\ \__/.\_\ \_\ \_\ \____\\ \_\
        \/_____/\/__/\/__/\/_/\/_/\/_/\/____/ \/_/

    The Holder of Stakes.

    Collecting 12.345 NU from staking rewards...

    OK | 0xb0625030224e228198faa3ed65d43f93247cf6067aeb62264db6f31b5bf411fa (55062 gas)
    Block #1245170 | 0x63e4da39056873adaf869674db4002e016c80466f38256a4c251516a0e25e547
     See https://goerli.etherscan.io/tx/0xb0625030224e228198faa3ed65d43f93247cf6067aeb62264db6f31b5bf411fa

    Collecting 0.978 ETH from policy rewards...

    OK | 0xe6d555be43263702b74727ce29dc4bcd6e32019159ccb15120791dfda0975372 (25070 gas)
    Block #1245171 | 0x0d8180a69213c240e2bf2045179976d5f18de56a82f17a9d59db54756b6604e4
     See https://goerli.etherscan.io/tx/0xe6d555be43263702b74727ce29dc4bcd6e32019159ccb15120791dfda0975372

You can run ``nucypher stake accounts`` to verify that your staking compensation
is indeed in your wallet. Use your favorite Ethereum wallet (MyCrypto or Metamask
are suitable) to transfer out the compensation earned (NU tokens or ETH) after
that.

Note that you will need to confirm two transactions if you collect both types of
staking compensation if you use a hardware wallet.

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


Or to set a worker:

.. code:: bash

    (nucypher)$ nucypher stake set-worker --hw-wallet --allocation-filepath PATH


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
