=======================
NuCypher Staking Guide
=======================

The account which is actively doing staking operations is necessary to be a hot
wallet. But it doesn't have to be the same account as the one which receives and
sends NU tokens. The account which holds NU tokens is called StakeHolder, or
Staker, and the account which participates in the network as Ursula node is
called Worker.
StakeHolder and Worker can have the same Ethereum account, but it's better to
have them separate: StakeHolder controlled by a hardware wallet, and Worker
having an address controlled by geth.

All staking-related operations done by StakeHolder are performed through the ``nucypher stake`` command:

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
|  ``divide``          | Create a new stake from part of an existing one                               |
+----------------------+-------------------------------------------------------------------------------+
| ``collect-reward``   | Withdraw staking or policy rewards                                            |
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


Staking Overview
-----------------


Most stakers on the Goerli testnet will complete the following steps:

1) Install nucypher on StakeHolder node https://docs.nucypher.com/en/latest/guides/installation_guide.html
2) Install and run Geth, Parity or another ethereum node (can use with software or hardware Ethereum wallet).
3) Request testnet tokens from faucet
4) Stake tokens (See Below)
5) Install another Ethereum node at the Worker instance
6) Initialize a Worker node and bond it to your Staker (``set-worker``) :ref:`ursula-config-guide`
7) Configure and run the Worker, and keep it online (See Below)!

Interactive Method
------------------

Run an Ethereum node for stakeholder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Assuming you have ``geth`` installed, let's run a node on Görli testnet.
On StakeHolder side, it's ok to run a light node.

.. code:: bash

    $ geth --goerli --syncmode light

If you want to use your hardware wallet, just connect it to your machine. You'll
see something like this in logs:

.. code:: bash

    INFO [08-30|15:50:39.153] New wallet appeared      url=ledger://0001:000b:00      status="Ethereum app v1.2.7 online"

If you see something like ``New wallet appeared, failed to open`` in the logs,
you need to reconnect the hardware wallet (without turning the ``geth`` node
off).

If you don't have a hardware wallet, you can create a software one:

.. code:: bash

    $ geth attach /home/<username>/.ethereum/goerli/geth.ipc
    > personal.newAccount();
    > eth.accounts
    ["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]

Where ``0x287a817426dd1ae78ea23e9918e2273b6733a43d`` is your newly created
account address and ``<username>`` is your user.

Initialize a new stakeholder
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake init-stakeholder --provider <PROVIDER>  --poa

If you ran ``geth`` node as above, your ``<PROVIDER>`` is
``ipc:///home/<username>/.ethereum/goerli/geth.ipc``.

Initialize a new stake
~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake create

    Select staking account [0]: 0
    Enter password to unlock 0xbb01c4fE50f91eF73c5dD6eD89f38D55A6b1EdCA:
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

    Escrow Address ... 0xBc6297c0781C25A9Bc44eEe22181C98a30DC0229
    Approve .......... 0xa74ac03a5500fc549636f9b0c44d0dc415e8fc0df4c648cb7386e4b95c4f3a3e
    Deposit .......... 0x341e406b77ff0f3a0e98982d61814fd8af82d90c5cfe7bad5353e2b757c2d96e


    Successfully transmitted stake initialization transactions.


List existing stakes
~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake list

    ======================================= Active Stakes =========================================

    | ~ | Staker | Worker | # | Value    | Duration     | Enactment
    |   | ------ | ------ | - | -------- | ------------ | -----------------------------------------
    | 0 | 0xbb01 | 0xdead | 0 | 15000 NU | 41 periods . | Aug 04 12:15:16 CEST - Sep 13 12:15:16 CEST
    | 1 | 0xbb02 | 0xbeef | 1 | 15000 NU | 30 periods . | Aug 20 12:15:16 CEST - Sep 18 12:15:16 CEST
    | 2 | 0xbb03 | 0x0000 | 0 | 30000 NU | 30 periods . | Aug 09 12:15:16 CEST - Sep 9 12:15:16 CEST

If the Worker in the list is shown as ``0x0000``, it means that you didn't yet
attach any node to your Staker, so you still have to do it!


Bond an Ursula to a Staker
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After you created an Ethereum node for your worker (see below about the worker),
you can set the worker:

.. code:: bash

    (nucypher)$ nucypher stake set-worker

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

Please note that the address should be in the format where checksum is encoded
in the address. However, geth shows addresses in the lower case. You can convert
by copying and pasting the address to `Goerli Etherscan <https://goerli.etherscan.io/>`_, e.g.
``0x287a817426dd1ae78ea23e9918e2273b6733a43d -> 0x287A817426DD1AE78ea23e9918e2273b6733a43D``.

After this step, you're finished with the Staker, and you can proceed to :ref:`ursula-config-guide`.


Divide an existing stake
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake divide

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


Inline Method
--------------

+----------------+----------------+--------------+
| Option         | Flag           | Description  |
+================+================+==============+
| stake value    | ``--value``    | in NU        |
+----------------+----------------+--------------+
| stake duration | ``--duration`` | in periods   |
+----------------+----------------+--------------+
| stake index    | ``--index``    | to divide    |
+----------------+----------------+--------------+


Stake 30000 NU for 90 Periods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake init --value 30000 --duration 90
    ...


Divide stake at index 0, at 15000 NU for 30 additional Periods
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code:: bash

    (nucypher)$ nucypher stake divide --index 0 --value 15000 --duration 30
    ...

Worker configuration
------------------------

Please go to :ref:`ursula-config-guide`.
