Sub-stakes
==========

A staker may extend the unlock period for any number of portions of their total stake. This divides the stake into smaller parts, each with a unique unlock date in the future. Stakers may also acquire and lock new tokens. The total stake is represented as the sum of all the different sub-stakes active in a given cycle (new cycle every 24h), which includes locked sub-stakes, and any sub-stakes that have passed their unlock date, and can be freely withdrawn. Each sub-stake has a beginning and duration (lock time). When a staker confirms activity each day and winding down is enabled, the remaining lock time for relevant sub-stakes is reduced.

A sub-stake remains active until it becomes unlocked, and a staker gets the reward for the last period by calling ``mint()`` or ``confirmActivity()`` once the last period is surpassed. Each staker can have no more than 30 active sub-stakes which are stored in an array. All sub-stake changes initially reuse slots of inactive sub-stakes for storage in the array, and if there are none, will instead use empty slots. Therefore, attempting to retrieve data about previous inactive sub-stakes is not guaranteed to be successful since the data could have been overwritten.



Operations that modify the sub-stake array
------------------------------------------

Deposit and locking
^^^^^^^^^^^^^^^^^^^
*Methods* : ``deposit(uint256,uint16)``,  ``deposit(address,uint256,uint16)``,  ``lock(uint256,uint16)``

To become a staker, NU tokens must be transferred to the ``StakingEscrow`` contract and locked using one of the ``deposit()`` methods. If the staker already has unlocked tokens within the account in the contract, then the stake can be locked using the ``lock()`` method. If successful, a new element will be created in the array of sub-stakes with the next period as the starting date, and the duration equal to the input parameter.


**Example:**

    A staker deposits 900 tokens:
        * 1st sub-stake = 900 tokens starting from the next period and locked for 5 periods

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         900|   +-------------------+
            |   |        1st        |   period
            +---+---+---+---+---+---+---->
            | 0 | 1 | 2 | 3 | 4 | 5 | 6



Lock prolongation
^^^^^^^^^^^^^^^^^
*Methods* : ``prolongStake(uint256,uint16)``

In order to increase the staking reward, as well as the possibility of obtaining policies with a longer timeframe, stakers can increase the duration of their locked sub-stake using the ``prolongStake()`` method. The number of sub-stakes does not change, but the locked duration for the specified sub-stake will be increased.

**Example:**

    A staker prolongs sub-stake for 2 additional periods up to 7:
		- Before: 
			* 1st sub-stake = 900 tokens for 5 periods
		- After: 
			* 1st sub-stake = 900 tokens for 7 periods

    .. aafig::
        :proportional:
        :textual:

                         Before             

            stake
            ^
            |
         900+-----------------------+
            |          1st          |   period
            +---+---+---+---+---+---+---->
            | 0 | 1 | 2 | 3 | 4 | 5 | 6      
			
			
			
                         After             

            stake
            ^
            |
         900+-------------------------------+
            |              1st              |   period
            +---+---+---+---+---+---+---+---+---->
            | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8
			
			
Sub-stake division
^^^^^^^^^^^^^^^^^^
*Methods* : ``divideStake(uint256,uint256,uint16)``

If necessary, stakers can extend the locking duration for only a portion of their tokens in a sub-stake by using the ``divideStake()`` method. This method splits a sub-stake into two elements: the old sub-stake with the reduced locked amount and the new sub-stake with the specified amount. The new sub-stake has the specified locked amount and an extended lock duration, based on the specified number of periods, with the same start period as the old sub-stake.

**Example:**

    A staker divides sub-stake and extends locking time for 300 tokens for 2 additional periods:
		- Before: 
			* 1st sub-stake = 900 tokens for 5 periods
		- After: 
			* 1st sub-stake = 600 tokens for 5 periods
			* 2nd sub-stake = 300 tokens for 7 periods

    .. aafig::
        :proportional:
        :textual:

                         Before             

            stake
            ^
            |
         900+-----------------------+
            |                       |
            |          1st          |
            |                       |   period
            +---+---+---+---+---+---+---->
            | 0 | 1 | 2 | 3 | 4 | 5 | 6       
			
			
			
                         After             

            stake
            ^
            |
         900+-----------------------+
            |                       |
            |          1st          |
         300+-----------------------+-------+
            |              2nd              |   period
            +---+---+---+---+---+---+---+---+---->
            | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8
   


Slashing
^^^^^^^^
*See:* `the slashing protocol`_ 

.. _`the slashing protocol`: https://docs.nucypher.com/en/latest/architecture/slashing.html




Flags that affect the sub-stake array
-------------------------------------

Re-staking
^^^^^^^^^^
*Used in methods* : ``confirmActivity()``, ``mint()``

When re-staking is turned off, the number of locked tokens in sub-stakes does not change by itself.
However, when re-staking is enabled (default) then all staking rewards are re-locked as part of each relevant sub-stake (inside ``confirmActivity()`` and/or ``mint()``).  Consequently, each such sub-stake has an increased locked amount (by reward) and the number of sub-stakes remains unchanged.

**Example:**

    A staker has few sub-stakes and calls ``mint()``. Assume that thus far the 1st and 2nd sub-stakes will produce 50 tokens and 20 tokens respectively in rewards:
		- Before calling: 
			* 1st sub-stake = 400 tokens for 8 periods
			* 2nd sub-stake = 200 tokens for 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
			* 100 tokens in an unlocked state
		- After calling, if re-staking is disabled:  
			* 1st sub-stake = 400 tokens for 8 periods
			* 2nd sub-stake = 200 tokens for 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
			* 170 tokens in an unlocked state
		- After calling, if re-staking is enabled: 
			* 1st sub-stake = 450 tokens for 8 periods
			* 2nd sub-stake = 220 tokens for 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
			* 100 tokens in an unlocked state

    .. aafig::
        :proportional:
        :textual:

                             Before             

            stake
            ^
            |
         700|   +-------+
            |   |  3rd  |
         600+---+-------+
         500|           +-----------+
            |    2nd    |    3rd    |
         400+-----------+-----------+-----------+
            |                                   |
            |                1st                |   period
            +---+---+---+---+---+---+---+---+---+---->    
            | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
			
			
			
			
                         After, re–staking is enabled             

            stake
            ^
            |
         770|   +-------+
            |   |  3rd  |
         670+---+-------+
            |           |
         550|    2nd    +-----------+
            |           |    3rd    |
         450+-----------+-----------+-----------+
            |                                   |
            |                1st                |
            |                                   |   period
            +---+---+---+---+---+---+---+---+---+---->    
            | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
			


Winding down
^^^^^^^^^^^^
*Used in methods* : ``confirmActivity()``

A disabled "winding down" parameter (default) guarantees that the worker must call ``confirmActivity()`` at least N times after the parameter is enabled to unlock the sub-stake, where N is the locking duration of sub-stake. When disabled, the unlock date for each sub-stakes shifts forward by 1 period after each period i.e. the duration continues to remain the same until the parameter is enabled. Once the "winding down" parameter is enabled, each call to ``confirmActivity()`` (no more than once in a period) leads to a reduction of locking duration for each sub-stake, and the unlock date no longer changes.

**Example:**

    A staker has few sub-stakes, worker calls ``сonfirmActivity()`` each period:
		- Current period: 
			* 1st sub-stake = 400 tokens for 8 periods
			* 2nd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
		- Next period, if winding down is disabled:  
			* 1st sub-stake = 400 tokens for 8 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and locked for 5 future periods
		- Next period, if winding down is enabled: 
			* 1st sub-stake = 400 tokens for 7 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and locked for 4 future periods

    .. aafig::
        :proportional:
        :textual:
			
                         Current period           

            stake
            ^
            |
         500|   +-------------------+
            |   |        2nd        |
         400+---+-------------------+-----------+
            |                                   |
            |                1st                |
            |                                   |   period
            +---+---+---+---+---+---+---+---+---+---->    
            | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9
		
			
			
                     Next period, winding down is disabled   

            stake
            ^
            |
         500+-----------------------+
            |         2nd           |
         400+-----------------------+-----------+
            |                                   |
            |                1st                |
            |                                   |   period
            +---+---+---+---+---+---+---+---+---+---->    
            | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10        

			
			
                     Next period, winding down is enabled     

            stake
            ^
            |
         500+-------------------+
            |        2nd        |
         400+-------------------+-----------+
            |                               |
            |              1st              |
            |                               |   period
            +---+---+---+---+---+---+---+---+---->    
            | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9        
