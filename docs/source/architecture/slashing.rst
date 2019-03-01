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

A staker may extend the unlock period for any number of portions of their total stake. This divides the stake into smaller parts, each with a unique unlock date in the future. Stakers may also acquire and lock new tokens. The total stake is represented as the sum of all the different sub-stakes active in a given cycle (new cycle every 24h), which includes locked sub-stakes, and any sub-stakes that have passed their unlock date, and can be freely withdrawn. Each sub-stake has a beginning and duration (lock time). When a staker confirms activity each day, the remaining lock time for relevant sub-stakes is reduced. 

Sub stakes get slashed in the order of their remaining lock time, beginning with the shortest – so the first portion of the stake to be slashed is the unlocked portion. After that, if necessary, locked sub-stakes are decreased – the shortest sub stake is decreased by the required amount; if the adjustment of that sub-stake is insufficient to fulfil the required punishment sum, then the next shortest sub-stake is decreased, and so on. Sub-stakes that begin in the next period are checked separately.

**Example:**

A staker has 1000 tokens:
	* 1st sub stake = 500 tokens locked for 10 periods
	* 2nd sub stake = 200 tokens for 2 periods
	* 3rd sub stake = 100 tokens locked starting from the next period
	* 200 tokens in an unlocked state (still staked, but can be freely withdrawn).

Penalty Scenarios:

* *Scenario 1*: Staker incurs penalty calculated to be worth **100 tokens**:

	Only the unlocked tokens will be reduced; from 200 to 100. The values of locked sub-stakes will therefore remain unchanged in this punishment scenario. 

	Result:

		* 1st sub stake = 500 tokens locked for 10 periods
		* 2nd sub stake = 200 tokens for 2 periods
		* 3rd sub stake = 100 tokens locked starting from the next period
		* 100 tokens in an unlocked state
   
* *Scenario 2*: Staker incurs penalty calculated to be worth **400 tokens**:

	The remaining tokens can only cover 200 tokens. In the current period, 700 tokens are locked and 800 tokens are locked for the next period. The 3rd sub stake is locked for the next period but has not yet been used as a deposit for "work" - not until the next period begins. Therefore, it will be the next sub stake to be slashed. However, it can only cover 100 tokens for the penalty which is still not enough. The next shortest locked sub stake (2nd) is then reduced by 100 tokens to cover the remainder of the penalty, and the other sub stakes remain unchanged.

	Result:

		* 1st sub stake = 500 tokens locked for 10 periods
		* 2nd sub stake = 100 tokens for 2 periods
		* 3rd sub stake = 0 tokens locked starting from the next period
		* Remaining 0 tokens
 
* *Scenario 3*: Staker incurs penalty calculated to be worth **600 tokens**:

	Reducing the unlocked remaining tokens, 3rd sub stakes, and the shortest sub stake (2nd) is not enough, so they are all removed. The next shortest sub stake is the 1st which is reduced from 500 to 400.

	Result:

		* 1st sub stake = 400 tokens locked for 10 periods
		* 2nd sub stake = 0 tokens for 2 periods
		* 3rd sub stake = 0 tokens locked starting from the next period
		* Remaining 0 tokens
