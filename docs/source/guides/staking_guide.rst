=======================
NuCypher Staking Guide
=======================

**Ursula Staking Actions**

+-------------------+-------------------------------------------------------------------------+
| Action            |  Description                                                            |
+===================+=========================================================================+
|  `stake`          | Initialize or view NuCpher stakes (used with `--value` and `--duration`)|
+-------------------+-------------------------------------------------------------------------+
|  `divide-stake`   | Divide stake, used with `--value` and `--duration`                      |
+-------------------+-------------------------------------------------------------------------+
|  `collect-reward` | Collect staking reward (Policy reward collection in future PR)          |
+-------------------+-------------------------------------------------------------------------+


**Ursula Staking Options**

+----------------+----------------------------------------+
| Option         |  Description                           |
+================+========================================+
|  `--value`     | Stake value                            |
+----------------+----------------------------------------+
|  `--duration`  | Stake duration of extension            |
+----------------+----------------------------------------+
|  `--index`     | Stake index                            |
+----------------+----------------------------------------+
|  `--list`      | List stakes (used with `stake` action) |
+----------------+----------------------------------------+



Interactive Method
------------------

.. code:: bash

    (nucypher)$ nucypher ursula stake


*Initial a new stake*

.. code:: bash

    Stage a new stake? [y/N]: y

    Current balance: 100000
    Enter stake value in NU [15000]: 30000

    Minimum duration: 30 | Maximum Duration: 365
    Enter stake duration in periods (1 Period = 24 Hours): 90

    ============================== STAGED STAKE ==============================

    (Ursula)⇀Sienna Scales GreenYellow Ferry↽ (0x058D5F4cC9d52403c2F6944eC1c821a0e6E78657)
    ~ Value      -> 30000 NU (300000000000000000000000 NU-wei)
    ~ Duration   -> 90 Days (90 Periods)
    ~ Enactment  -> 2019-03-12 02:08:41.425755+00:00 (17967)
    ~ Expiration -> 2020-02-08 02:08:41.425912+00:00 (18300)

    =========================================================================

    * Ursula Node Operator Notice *
    -------------------------------
    ...

    Accept node operator obligation? [y/N]: y
    Publish staged stake to the blockchain? [y/N]: y

    Escrow Address ... 0x709166C66Ab0BC36126607BE823F11F64C2A9996
    Approve .......... 0x7eef13ee7451adaa33d814ecd4953a46de0a10267f7b52dcb487031c900a8d80
    Deposit .......... 0x75127e862e044309c9980fdb0e4d3120de7723dd8b70f62d5504e6851f672f4c

    Successfully transmitted stake initialization transactions.
    View your active stakes by running 'nucypher ursula stake --list'
    or start your Ursula node by running 'nucypher ursula run'.


*View existing stakes*

.. code:: bash

    (nucypher)$ nucypher ursula stake --list

    | # | Duration     | Enact     | Expiration   | Value
    | - | ------------ | --------- | -------------| -----
    | 0 | 32 periods . | yesterday | 14 Apr ..... | 30000 NU


*Divide an existing stake*

.. code:: bash

    (nucypher)$ nucypher ursula divide-stake


    | # | Duration     | Enact     | Expiration | Value
    | - | ------------ | --------- | -----------| -----
    | 0 | 32 periods . | yesterday | 14 Apr ... | 30000 NU

    Select a stake to divide: 0
    Enter target value (must be less than 3000 NU): 1500
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


*Stake 3000 NU for 90 Periods*

.. code:: bash

    (nucypher)$ nucypher ursula stake --value 3000 --duration 90
    ...


*Divide stake at index 0, at 1500 NU for 30 additional Periods*

.. code:: bash

    (nucypher)$ nucypher ursula divide-stake --index 0 --value 1500 --duration 30
    ...