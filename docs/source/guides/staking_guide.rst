=======================
NuCypher Staking Guide
=======================

**StakeHolder Commands**

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``new-stakeholder`` | Create a new stakeholder configuration                                        |
+----------------------+-------------------------------------------------------------------------------+
|  ``init``            | Initialize or view NuCypher stakes (used with ``--value`` and ``--duration``) |
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


**StakeHolder Command Options**

+-----------------+--------------------------------------------+
| Option          |  Description                               |
+=================+============================================+
|  ``--value``    | Stake value                                |
+-----------------+--------------------------------------------+
|  ``--duration`` | Stake duration of extension                |
+-----------------+--------------------------------------------+
|  ``--index``    | Stake index                                |
+-----------------+--------------------------------------------+



Interactive Method
------------------

*Initialize a new stakeholder*

.. code:: bash

    (nucypher)$ nucypher stake new-stakeholder


*Initialize a new stake*

.. code:: bash

    (nucypher)$ nucypher stake init

*List existing stakes*

.. code:: bash

    (nucypher)$ nucypher ursula stake --list

    | # | Duration     | Enact     | Expiration   | Value
    | - | ------------ | --------- | -------------| -----
    | 0 | 32 periods . | yesterday | 14 Apr ..... | 30000 NU


*Divide an existing stake*

.. code:: bash

    (nucypher)$ nucypher ursula stake --divide


    | # | Duration     | Enact     | Expiration | Value
    | - | ------------ | --------- | -----------| -----
    | 0 | 32 periods . | yesterday | 14 Apr ... | 30000 NU

    Select a stake to divide: 0
    Enter target value (must be less than 30000 NU): 15000
    Enter number of periods to extend: 30

    ============================== ORIGINAL STAKE ============================

    ~ Original Stake: | 0 | 90 periods . | yesterday .. | 14 Apr ... | 30000 NU

    ============================== STAGED STAKE ==============================

    (Ursula)⇀Sienna Scales GreenYellow Ferry↽ (0x058D5F4cC9d52403c2F6944eC1c821a0e6E78657)
    ~ Value      -> 15000 NU (15000000000000000000000 NU-wei)
    ~ Duration   -> 120 Days (120 Periods)
    ~ Enactment  -> 2019-03-13 20:18:17.306398+00:00 (period #17968)
    ~ Expiration -> 2019-04-24 20:18:17.306801+00:00 (period #18010)

    =========================================================================



Inline Method
--------------

+----------------+------------+--------------+
| Option         | Flag       | Description  |
+================+============+==============+
| stake value    | --value    | in NU        |
+----------------+------------+--------------+
| stake duration | --duration | in periods   |
+----------------+------------+--------------+
| stake index    | --index    | to divide    |
+----------------+------------+--------------+


*Stake 30000 NU for 90 Periods*

.. code:: bash

    (nucypher)$ nucypher ursula stake --value 30000 --duration 90
    ...


*Divide stake at index 0, at 15000 NU for 30 additional Periods*

.. code:: bash

    (nucypher)$ nucypher ursula stake --divide --index 0 --value 15000 --duration 30
    ...