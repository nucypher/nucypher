.. _stake-management:

Stake Management
----------------

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
|  ``merge``           | Merge two stakes into one                                                     |
+----------------------+-------------------------------------------------------------------------------+
|  ``remove-inactive`` | Remove unused/inactive stakes                                                 |
+----------------------+-------------------------------------------------------------------------------+
|  ``rewards``         | Preview and withdraw staking rewards                                          |
+----------------------+-------------------------------------------------------------------------------+
|  ``events``          | View blockchain events associated with a staker                               |
+----------------------+-------------------------------------------------------------------------------+


Re-staking
~~~~~~~~~~~

As your Ursula performs work, all rewards are automatically added to your existing stake to optimize earnings.
This feature, called `re-staking`, is **enabled** by default.

To disable re-staking:

.. code:: bash

    (nucypher)$ nucypher stake restake --disable

To enable re-staking again:

.. code:: bash

    (nucypher)$ nucypher stake restake --enable


.. _staking-prolong:

Prolong
~~~~~~~

Existing stakes can be extended by a number of periods as long as the resulting
stake's duration is not shorter than the minimum. To prolong an existing stake's duration:

.. code:: bash

    (nucypher)$ nucypher stake prolong --hw-wallet

    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 30000 NU │           5 │ Mar 24 2021 │ Apr 21 2021   │  1.10x │ DIVISIBLE │
    ├───────┼──────────┼─────────────┼─────────────┼───────────────┼────────┼───────────┤
    │     1 │ 15000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ EDITABLE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛
    Select Stake (0, 1): 0
    Enter number of periods to extend (1-62859): 4
    Publish stake extension of 4 period(s) to the blockchain? [y/N]: y
    Broadcasting PROLONGSTAKE Transaction (0.012197658 ETH @ 274 gwei)
    TXHASH 0x049b98200c5949b75aa265ad4155f4ba02cb17a0309b16093bd7003c59fefb74
    Waiting 600 seconds for receipt
    Successfully Prolonged Stake
    ...


    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 30000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ DIVISIBLE │
    ├───────┼──────────┼─────────────┼─────────────┼───────────────┼────────┼───────────┤
    │     1 │ 15000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ EDITABLE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛


Wind Down
~~~~~~~~~

The proportion of staking rewards received by a staker depends on the
stake size and the remaining locked duration.

When wind down is enabled, the locked duration decreases after each period which results
in reduced staking yield. When disabled, the stake's locked duration remains
constant and improves staking yield.
See :ref:`sub-stake-winddown` for more information.

Wind down is **disabled** by default.

.. note:: WorkLock participants have wind down **enabled** by default.

To start winding down an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake winddown --enable


To stop winding down:

.. code:: bash

    (nucypher)$ nucypher stake winddown --disable


Snapshots
~~~~~~~~~

Taking snapshots is *enabled* by default. Snapshots must be enabled to participate in the DAO, but it has a slight cost in gas every time your staking balance changes. To stop taking snapshots:

.. code:: bash

    (nucypher)$ nucypher stake snapshots --disable

To enable snapshots again:

.. code:: bash

    (nucypher)$ nucypher stake snapshots --enable



Divide
~~~~~~

Existing stakes can be divided into smaller :ref:`sub-stakes <sub-stakes>`, with different values and durations. Dividing a stake
allows stakers to accommodate different liquidity needs since sub-stakes can have different durations. Therefore, a
staker can liquidate a portion of their overall stake at an earlier time.

To divide an existing stake:

.. code:: bash

    (nucypher)$ nucypher stake divide --hw-wallet
    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):
    NOTE: Showing divisible stakes only

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    Select Stake (0): 0
    Enter target value (15000 NU - 30000 NU): 15000
    Enter number of periods to extend: 4

    ══════════════════════════════ ORIGINAL STAKE ════════════════════════════

    Staking address: 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf
    ~ Original Stake: | - | 0xB548 | 0 | 45000 NU | 4 periods  | Mar 24 17:00 PDT - Apr 21 17:00 PDT


    ══════════════════════════════ STAGED STAKE ══════════════════════════════

    Staking address: 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf
    ~ Chain      -> ID <CHAIN_ID>
    ~ Value      -> 15000 NU (15000000000000000000000 NuNits)
    ~ Duration   -> 56 Days (8 Periods)
    ~ Enactment  -> Mar 24 2021 17:00 PDT (period #2673)
    ~ Expiration -> May 19 2021 17:00 PDT (period #2681)

    ═════════════════════════════════════════════════════════════════════════
    Publish stake division to the blockchain? [y/N]: y
    Broadcasting DIVIDESTAKE Transaction (0.019689812 ETH @ 273.5 gwei)
    TXHASH 0x641029fcfd4e263dc38774c5510f539f50c00004941ed0c4c737e53b67ade024
    Waiting 600 seconds for receipt
    Successfully divided stake
    ...


    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 30000 NU │           5 │ Mar 24 2021 │ Apr 21 2021   │  1.10x │ DIVISIBLE │
    ├───────┼──────────┼─────────────┼─────────────┼───────────────┼────────┼───────────┤
    │     1 │ 15000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ EDITABLE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛


Increase
~~~~~~~~

Existing stakes can be increased by an amount of NU as long as the resulting
staker's locked value is not greater than the maximum. To increase an existing stake's value:

.. code:: bash

    (nucypher)$ nucypher stake increase --hw-wallet


Merge
~~~~~

Two stakes with the same final period can be merged into one stake.
This can help to decrease gas consumption in some operations. To merge two stakes:

.. code:: bash

    (nucypher)$ nucypher stake merge --hw-wallet
    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 30000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ DIVISIBLE │
    ├───────┼──────────┼─────────────┼─────────────┼───────────────┼────────┼───────────┤
    │     1 │ 15000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ EDITABLE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛
    Select Stake (0, 1): 0
    NOTE: Showing stakes with 2680 final period only

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     1 │ 15000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ EDITABLE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛
    Select Stake (1): 1
    Publish merging of 0 and 1 stakes? [y/N]: y
    Broadcasting MERGESTAKE Transaction (0.013509688 ETH @ 278 gwei)
    TXHASH 0xef5ac787a22fc9a0a3e13a173e6e6db7603ec0be4473084d8b2b06a414328d62
    Waiting 600 seconds for receipt
    Successfully Merged Stakes
    ...

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 45000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ DIVISIBLE │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛
    Note that some sub-stakes are inactive: [1]
    Run `nucypher stake list --all` to show all sub-stakes.
    Run `nucypher stake remove-inactive --all` to remove inactive sub-stakes; removal of inactive sub-stakes will reduce commitment gas costs.



Remove inactive sub-stake
~~~~~~~~~~~~~~~~~~~~~~~~~

When sub-stakes terminate, are merged or edited,
there may be 'unused', inactive sub-stakes remaining on-chain.
Continued tracking of these unused sub-stakes adds unnecessary gas costs to node commitment operations.
Consequently, removal of unused sub-stakes will reduce per period gas costs.

Unused sub-stakes can be displayed by listing all sub-stakes
and will be indicated by the ``INACTIVE`` status label.

.. code:: bash

    (nucypher)$ nucypher stake list --all --hw-wallet
    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 45000 NU │ 9           │ Mar 24 2021 │ May 19 2021   │  1.17x │ DIVISIBLE │
    ├───────┼──────────┼─────────────┼─────────────┼───────────────┼────────┼───────────┤
    │     1 │ 15000 NU │ N/A         │ Mar 24 2021 │ N/A           │  N/A   │ INACTIVE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛


To remove an unused sub-stake, run the following command and select the index
of your ``INACTIVE`` sub-stake:

.. code:: bash

    (nucypher)$ nucypher stake remove-inactive --hw-wallet
    Enter ethereum account password (0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf):
    Fetching inactive stakes

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     1 │ 15000 NU │ N/A         │ Mar 24 2021 │ N/A           │  N/A   │ INACTIVE  │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛

    Select Stake (1): 1
    Publish removal of 1 stake? [y/N]: y
    Broadcasting REMOVEUNUSEDSUBSTAKE Transaction (0.012804726 ETH @ 288.2 gwei)
    TXHASH 0x942a70ee2adb5078fa6d8fa468f28d3e35386f90247035fdb5d19c34836200a0
    Waiting 600 seconds for receipt
    Successfully Removed Stake
    ...

    Network <NETWORK_NAME> ═══════════════════════════════
    Staker 0xB548378f13e9A2C7bEf66B890B46F2eD6Ed87fCf ════
    Worker 0x6cf78fE4bD2a6573046d17f72f4C20462124Aa10 ════
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
    │     0 │ 45000 NU │           9 │ Mar 24 2021 │ May 19 2021   │  1.17x │ DIVISIBLE │
    ╘═══════╧══════════╧═════════════╧═════════════╧═══════════════╧════════╧═══════════╛


In order to make the operation as simple and cheap as possible,
the removal algorithm simply relocates the last active sub-stake to the slot
occupied by the currently inactive one, so you will notice a slight
re-ordering of your sub-stakes. This is normal and doesn't have any negative implications.

For your convenience, run ``nucypher stake remove-inactive --all`` to remove all inactive sub-stakes using
one CLI command to execute a series of removal transactions.


Collect Staker Rewards
~~~~~~~~~~~~~~~~~~~~~~

NuCypher nodes earn two types of rewards: staking rewards (in NU) and policy fees (i.e., service fees in ETH).
To collect these rewards use ``nucypher stake rewards withdraw`` with flags ``--tokens`` and ``--fees``
(or even both).

While staking rewards can only be collected to the original staker account, you can decide which account receives
policy fees using the ``--withdraw-address <ETH_ADDRESS>`` flag.

.. code:: bash

    (nucypher)$ nucypher stake rewards withdraw --tokens --fees --staking-address 0x270b3f8af5ba2B79ea3Bd6a6Efc7ecAB056d3E3f --hw-wallet
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


.. _staker_blockchain_events:

Query Staker Blockchain Events
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As the Staker and its associated Worker interact with the StakingEscrow smart contract, various on-chain events
are emitted. These events are outlined :doc:`here </contracts_api/main/StakingEscrow>`, and are made accessible via the
``nucypher stake events`` CLI command.


.. note::

    This command is limited to events from the StakingEscrow smart contract and the Staker address associated with
    the Staker's configuration file. For generic and network-wide event queries,
    see :doc:`/references/network_events`.


For simple Staker accounting, events such as ``CommitmentMade``, ``Withdrawn``, and ``Minted`` can
be used. The output of each can be correlated using the period number.

By default, the query is performed from block number 0 i.e. from the genesis of the blockchain. This can be modified
using the ``--from-block`` option.


For a full list of CLI options, run:

.. code::

    $ nucypher stake events --help


For example, to view all of the staking rewards received by the Staker thus far, run:

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --provider <PROVIDER URI> --event-name Minted

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11076964
      ...

``1234567890123456789012`` is in NuNits and equates to approximately 1234.57 NU (1 NU = 10\ :sup:`18` NuNits).


To view staking rewards received by the Staker from block number 11070000 to block number 11916688, run:

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --provider <PROVIDER URI> --event-name Minted --from-block 11070000 --to-block 11916688

    Reading Latest Chaindata...
    Retrieving events from block 11070000 to 11916688

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11076964
      ...


.. important::

    Depending on the Ethereum provider being used, the number of results a query is allowed to return may be limited.
    For example, on Infura this limit is currently 10,000.


To aid with management of this information, instead of outputting the information to the CLI, the event data can
be written to a CSV file using either of the following command-line options:

* ``--csv`` - flag to write event information to a CSV file in the current directory with a default filename
* ``--csv-file <FILEPATH>`` - write event information to a CSV file at the provided filepath

For example,

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --provider <PROVIDER URI> --event-name Minted --csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    StakingEscrow::Minted events written to StakingEscrow_Minted_2021-02-09_15-23-25.csv


.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --provider <PROVIDER URI> --event-name Minted --csv-file ~/Minted_Events.csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    StakingEscrow::Minted events written to /<HOME DIRECTORY>/Minted_Events.csv
