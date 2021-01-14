Stake Management
-----------------

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


Re-staking
~~~~~~~~~~~

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
~~~~~~~

Existing stakes can be extended by a number of periods as long as the resulting
stake's duration is not shorter than the minimum. To prolong an existing stake's duration:

.. code:: bash

    (nucypher)$ nucypher stake prolong --hw-wallet


Wind Down
~~~~~~~~~

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


Remove unused sub-stake
~~~~~~~~~~~~~~~~~~~~~~~

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
