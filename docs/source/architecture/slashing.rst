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

.. _`Sub-stakes`: https://docs.nucypher.com/en/latest/architecture/sub_stakes.html

The goal of slashing is to reduce the number of tokens that belongs to a staking offender. While the reduction of tokens is intended to be punitive, once the tokens have been slashed, the slashing algorithm attempts to preserve the most efficient use of the offenders' remaining tokens based on their existing `Sub-stakes`_. The main task is not to violate the logic of locking tokens.

An entire stake consists of:

    * unlocked tokens which the staker can withdraw at any moment
    * tokens locked for a specific period

In terms of how the stake is slashed, unlocked tokens are the first portion of the stake to be slashed. After that, if necessary, locked sub-stakes are decreased in order based on their remaining lock time, beginning with the shortest. The shortest sub-stake is decreased, and if the adjustment of that sub-stake is insufficient to fulfil the required punishment sum, then the next shortest sub-stake is decreased, and so on. Sub-stakes that begin in the next period are checked separately.

Sub-stakes for past periods cannot be slashed, so only the periods from now onward can be slashed. However, by design sub-stakes can't have a starting period that is after the next period, so all future periods after the next period will always have an amount of tokens less than or equal to the next period. The current period still needs to be checked since its stake may be different than the next period. Therefore, only the current period and the next period need to be checked for slashing.

Overall the slashing algorithm is as follows:

#. Reduce unlocked tokens

#. If insufficient, slash sub-stakes as follows:

    a. Calculate the maximum allowed total stake for any period for the staker ::

        max_allowed_stake = pre_slashed_total_stake - slashing_amount

       Therefore, for any period moving forward the sum of sub-stakes for that period cannot be more than ``max_allowed_stake``.
    b. For the current and next periods ensure that the amount of locked tokens is less than or equal to ``max_allowed_stake``. If not, then reduce the shortest sub-stake to ensure that this occurs; then the next shortest and so on, as necessary for the period.
    c. Since sub-stakes can extend over multiple periods and can only have a single fixed amount of tokens for all applicable periods (see `Sub-stakes`_), the resulting amount of tokens remaining in a sub-stake after slashing is the minimum amount of tokens it can have across all of its relevant periods. To clarify, suppose that a sub-stake is locked for periods ``n`` and ``n+1``, and the slashing algorithm first determines that the sub-stake can have 10 tokens in period ``n``, but then it can only have 5 tokens in period ``n+1``. In this case, the sub-stake will be slashed to have 5 tokens in both periods ``n`` and ``n+1``.
    d. The above property of sub-stakes means that there is the possibility that the total amount of locked tokens for a particular period could be reduced to even lower than the ``max_allowed_stake`` when unnecessary. Therefore, the slashing algorithm may create new sub-stakes on the staker's behalf to utilize tokens in the earlier period, when a sub-stake is needed to be reduced to an even lower value because of the next period. In the example above in c), the sub-stake was reduced to 5 tokens because of period ``n+1``, so there are 5 "extra" tokens `(10 - 5)` available in period ``n`` that can still be staked; hence, a new sub-stake with 5 tokens would be created to utilize these tokens in period ``n``. This benefits both the staker, by ensuring that their remaining tokens are efficiently utilized, and the network by maximizing its health.


To reinforce the algorithm, consider the following example stake and different slashing scenarios:

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
            |          |
         600|    2nd   +-------------+
            |          |     3rd     |
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
          800|     +----+
             |     | 3rd|
        700- +-----+----+ - - - - - - - - - - - - -
             |          |
          600|    2nd   +-------------+
             |          |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->

		
             stake
             ^
             |
             |     
        700- | - - +----+ - - - - - - - - - - - - -
             |     | 3rd|
          600+-----+----+-------------+
             |    2nd   |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
			 
		
             stake
             ^
             |
             |     
        700- +-----+----+ - - - - - - - - - - - - -
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
          800|     +----+
             |     | 3rd|
          700+-----+----+
             |          |
        600- |- -2nd- - +-------------+ - - - - - -
             |          |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->


             stake
             ^
             |
          700|     +----+
             |     | 3rd|
        600- +-----+----+-------------+ - - - - - -
             |    2nd   |     3rd     |
          500+----------+-------------+----------+
             |                                   |
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
			 

             stake
             ^
             |
        600- +-----+------------------+ - - - - - -
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
          800|     +----+
             |     | 3rd|
          700+-----+----+
             |          |
          600|    2nd   +-------------+
             |          |     3rd     |
          500+----------+-------------+----------+
        400- | - - - - - - - - - - - - - - - - - | -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
			 
			 
             stake
             ^
             |
          600|     +------------------+
             |     |       3rd        |
          500+-----+------------------+----------+
        400- | - - - - - - - - - - - - - - - - - | -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
			 
			 
             stake
             ^
             |
          500|     +------------------+
             |     |       3rd        |
        400- +-----+------------------+----------+ -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
			 
			 
             stake
             ^
             |
        400- +-----------------------------------+ -
             |               1st                 |
             |                                   |   period
             +-----------------------------------+--->
