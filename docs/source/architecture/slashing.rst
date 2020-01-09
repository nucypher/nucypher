The Slashing Protocol
=====================

TBD


Violations
----------

TBD


Calculating the slashing penalty
--------------------------------

TBD (https://github.com/nucypher/nucypher/issues/803)


How slashing affects stake
--------------------------

The goal of slashing is to reduce the number of tokens that belongs to a staking offender.
In this case, the main task is not to violate the logic of locking tokens.
The entire stake consists of:

    * tokens which the staker can withdraw at any moment
    * tokens locked for a specific period

.. _`Sub-stakes`: https://docs.nucypher.com/en/latest/architecture/sub_stakes.html

`Sub-stakes`_ get slashed in the order of their remaining lock time, beginning with the shortest – so the first portion of the stake to be slashed is the unlocked portion. After that, if necessary, locked sub-stakes are decreased – the shortest sub-stake is decreased by the required amount; if the adjustment of that sub-stake is insufficient to fulfil the required punishment sum, then the next shortest sub-stake is decreased, and so on. Sub-stakes that begin in the next period are checked separately.

**Example:**

    A staker has 1000 tokens:
        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 200 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods. The 3rd sub-stake is locked for the next period but has not yet been used as a deposit for "work" - not until the next period begins.
        * 200 tokens in an unlocked state (still staked, but can be freely withdrawn).

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         800|     +----+
            |     | 3rd|
         700+-----+----+
         600|          +-------------+
            |    2nd   |     3rd     |
         500+----------+-------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->
	

Penalty Scenarios:

* *Scenario 1*: Staker incurs penalty calculated to be worth **100 tokens**:

    Only the unlocked tokens will be reduced; from 200 to 100. The values of locked sub-stakes will therefore remain unchanged in this punishment scenario.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 200 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period
        * 100 tokens in an unlocked state

* *Scenario 2*: Staker incurs penalty calculated to be worth **300 tokens**:

    The unlocked tokens can only cover 200 tokens. In the current period, 700 tokens are locked and 800 tokens are locked for the next period. Therefore, we should reduce amount of locked tokens for the next period and leave unchanged locked amount in the current period. The 3rd sub-stake suits for this purpose but it's not the shortest one. So we take the 2nd sub-stake (the shortest), reduce it to 100 tokens and add new sub-stake with 100 tokens which active only in the current period.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 100 tokens for 2 periods
        * 3rd sub-stake = 100 tokens locked starting from the next period for 5 periods
        * 4rd sub-stake = 100 tokens for 1 period
        * Remaining 0 tokens

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         700+-----+----+
            | 4th | 3rd|
         600+-----+----+-------------+
            |    2nd   |     3rd     |
         500+----------+-------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->
   
* *Scenario 3*: Staker incurs penalty calculated to be worth **400 tokens**:

    The difference from the previous scenario is that should also decrease locked tokens in the current period. At the first step the 2nd sub-stake is reduced to 100 tokens. Next step - adjustment for the next period. The shortest sub-stake still the same - the 2nd. And we need to deacrese it from 100 to 0 only for the next period. Will be the same if we change duration of the 2nd sub-stake from 2 periods to 1 and the other sub-stakes remain unchanged.

    Result:

        * 1st sub-stake = 500 tokens locked for 10 periods
        * 2nd sub-stake = 100 tokens for 1 period
        * 3rd sub-stake = 100 tokens locked starting from the next period
        * Remaining 0 tokens

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         600+----------+-------------+
            |    2nd   |     3rd     |
         500+----------+-------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->
 
* *Scenario 4*: Staker incurs penalty calculated to be worth **600 tokens**:

    Reducing the unlocked remaining tokens, 3rd sub-stakes, and the shortest sub-stake (2nd) is not enough, so they are all removed. The next shortest sub-stake is the 1st which is reduced from 500 to 400.

    Result:

        * 1st sub-stake = 400 tokens locked for 10 periods
        * 2nd sub-stake = 0 tokens for 2 periods
        * 3rd sub-stake = 0 tokens locked starting from the next period
        * Remaining 0 tokens

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         400+-----------------------------------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->
