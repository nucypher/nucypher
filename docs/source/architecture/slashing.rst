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

    * unlocked tokens which the staker can withdraw at any moment
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

    The unlocked tokens can only cover 200 tokens worth of the penalty. Beyond that, the staker has 700 tokens currently locked and 100 tokens that will lock in the next period, meaning 800 tokens will be locked in total. In this scenario, we should reduce amount of locked tokens for the next period and leave unchanged locked amount in the current period. The 3rd sub-stake would be suitable to be reduced except that it's not the shortest, in terms of its unlock date. Instead, the 2nd sub-stake – the shortest (2 periods until unlock) – is reduced to 100 tokens and a new sub-stake with 100 tokens is added which is only active in the current period.

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

    The difference between this and the previous scenario is that the current period's sum of locked tokens is also reduced. The first step is to reduce the 2nd sub-stake to 100 tokens. Then, the next period is adjusted – the shortest sub-stake is still the 2nd – and it is reduced from 100 to zero for the next period. Notably, this would have the same result if we changed the duration of the 2nd sub-stake from 2 periods to 1 and the other sub-stakes remained unchanged.

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
         600+-----+------------------+
            | 2nd |       3rd        |
         500+-----+------------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->
 
* *Scenario 4*: Staker incurs penalty calculated to be worth **600 tokens**:

    The unlocked tokens, the 3rd sub-stake, and the shortest sub-stake (2nd) are all reduced to zero. This is not quite enough, so the next shortest sub-stake, the 1st, is also reduced from 500 to 400.

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
