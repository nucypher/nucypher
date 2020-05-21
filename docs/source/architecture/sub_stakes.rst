.. _sub-stakes:

Sub-stakes
==========

A staker may extend the unlock period for any number of portions of their total stake. This divides the stake into smaller parts, each with a unique unlock date in the future. Stakers may also acquire and lock new tokens. The total stake is represented as the sum of all the different sub-stakes active in a given period (new period every 24h), which includes locked sub-stakes, and any sub-stakes that have passed their unlock date, and can be freely withdrawn. 

Each sub-stake has:

    * **Locked amount of tokens**

        The locked amount of tokens is fixed for all applicable periods, i.e., it is not possible for a single sub-stake to have a different amount of tokens locked for different periods. To facilitate such a scenario, sub-stakes would need to be divided, see `Sub-stake division`_.

    * **Starting period**

        The period that the sub-stake begins its locking duration.

    * **Locking duration**

        Locking duration is defined to be the required number of times that ``commitToNextPeriod()`` needs to be called so that the sub-stake is registered as locked for the subsequent period. For example, if a sub-stake has a *locking duration of 5 periods* it means that the sub-stake will be locked for periods: 1,2,3,4,5 because ``commitToNextPeriod()`` would be called during periods 0,1,2,3,4 each time making a commitment for the subsequent period (1,2,3,4,5) respectively. Unless the starting period is specified, the sub-stake is considered locked for the 0th (current) period by default.


A sub-stake remains active until it becomes unlocked, and a staker gets the reward for the last period by calling ``mint()`` or ``commitToNextPeriod()`` once the last period is surpassed. Each staker can have no more than 30 active sub-stakes which are stored in an array. All sub-stake changes initially reuse slots of inactive sub-stakes for storage in the array, and if there are none, will instead use empty slots. Therefore, attempting to retrieve data about previous inactive sub-stakes is not guaranteed to be successful since the data could have been overwritten.


Operations that modify the sub-stake array
------------------------------------------

Deposit and locking
^^^^^^^^^^^^^^^^^^^
*Methods* : ``deposit(uint256,uint16)``,  ``deposit(address,uint256,uint16)``,  ``lock(uint256,uint16)``

To become a staker, NU tokens must be transferred to the ``StakingEscrow`` contract and locked using one of the ``deposit()`` methods. If the staker already has unlocked tokens within the account in the contract, then the stake can be locked using the ``lock()`` method. If successful, a new element will be created in the array of sub-stakes with the next period as the starting date, and the duration equal to the input parameter.


**Example:**

    A staker deposits 900 tokens:
        * 1st sub-stake = 900 tokens starting from the next period and a locking duration of 5 periods

    .. code::

            stake
            ^
            |
         900|   +-------------------+
            |   |        1st        |   period
            +---+---+---+---+---+---+---->
            + 0 + 1 + 2 + 3 + 4 + 5 + 6



Lock prolongation
^^^^^^^^^^^^^^^^^
*Methods* : ``prolongStake(uint256,uint16)``

In order to increase the staking reward, as well as the possibility of obtaining policies with a longer timeframe, stakers can increase the duration of their locked sub-stake using the ``prolongStake()`` method. The number of sub-stakes does not change, but the locked duration for the specified sub-stake will be increased.

**Example:**

    A staker prolongs sub-stake for 2 additional periods up to 7:
		- Before: 
			* 1st sub-stake = 900 tokens with locking duration of 5 periods
		- After: 
			* 1st sub-stake = 900 tokens with locking duration of 7 periods

    .. code::

                         Before             

            stake
            ^
            |
         900+-----------------------+
            |          1st          |   period
            +---+---+---+---+---+---+---->
            + 0 + 1 + 2 + 3 + 4 + 5 + 6      
			
			
			
                         After             

            stake
            ^
            |
         900+-------------------------------+
            |              1st              |   period
            +---+---+---+---+---+---+---+---+---->
            + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8
			
			
Sub-stake division
^^^^^^^^^^^^^^^^^^
*Methods* : ``divideStake(uint256,uint256,uint16)``

If necessary, stakers can extend the locking duration for only a portion of their tokens in a sub-stake by using the ``divideStake()`` method. This method splits a sub-stake into two elements: the old sub-stake with the reduced locked amount and the new sub-stake with the specified amount. The new sub-stake has the specified locked amount and an extended lock duration, based on the specified number of periods, with the same start period as the old sub-stake.

**Example:**

    A staker divides sub-stake and extends locking time for 300 tokens for 2 additional periods:
		- Before: 
			* 1st sub-stake = 900 tokens with locking duration of 5 periods
		- After: 
			* 1st sub-stake = 600 tokens with locking duration of 5 periods
			* 2nd sub-stake = 300 tokens with locking duration of 7 periods

    .. code::

                         Before             

            stake
            ^
            |
         900+-----------------------+
            |                       |
            |          1st          |
            |                       |   period
            +---+---+---+---+---+---+---->
            + 0 + 1 + 2 + 3 + 4 + 5 + 6       
			
			
			
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
            + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8
   


Slashing
^^^^^^^^
*See:* :ref:`slashing-protocol` 



Flags that affect the sub-stake array
-------------------------------------

.. _sub-stake-restaking:

Re-staking
^^^^^^^^^^
*Used in methods* : ``commitToNextPeriod()``, ``mint()``

When re-staking is disabled, the number of locked tokens in sub-stakes does not change by itself.
However, when re-staking is enabled (default) then all staking rewards are re-locked as part of each relevant sub-stake (inside ``commitToNextPeriod()`` and/or ``mint()``).  Consequently, each such sub-stake has an increased locked amount (by the accrued staking reward) and the number of sub-stakes remains unchanged.

**Example:**

    A staker has few sub-stakes and calls ``mint()``. Assume that thus far the 1st and 2nd sub-stakes will produce 50 tokens and 20 tokens respectively in rewards:
		- Before calling: 
			* 1st sub-stake = 400 tokens with locking duration of 8 periods
			* 2nd sub-stake = 200 tokens with locking duration of 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and a locking duration of 5 periods
			* 100 tokens in an unlocked state
		- After calling, if re-staking is disabled:  
			* 1st sub-stake = 400 tokens with locking duration of 8 periods
			* 2nd sub-stake = 200 tokens with locking duration of 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and a locking duration of 5 periods
			* 170 tokens in an unlocked state
		- After calling, if re-staking is enabled: 
			* 1st sub-stake = 450 tokens with locking duration of 8 periods
			* 2nd sub-stake = 220 tokens with locking duration of 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and a locking duration of 5 periods
			* 100 tokens in an unlocked state

    .. code::

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
            + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9
			
			
			
			
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
            + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9
			

.. _sub-stake-winddown:

Winding down
^^^^^^^^^^^^
*Used in methods* : ``commitToNextPeriod()``

An enabled "winding down" parameter means that each call to ``commitToNextPeriod()`` (no more than once in a period) leads to a reduction of the locking duration for each sub-stake. In other words, the sub-stake will unlock after the worker calls ``commitToNextPeriod()`` at least N times (no more than once in a period), where N is the locking duration of sub-stake. When disabled (default), the unlock date for each sub-stakes shifts forward by 1 period after each period. In other words, the duration continues to remain the same until the "winding down" parameter is enabled.

**Example:**

    A staker has few sub-stakes, worker calls ``commitToNextPeriod()`` each period:
		- Current period: 
			* 1st sub-stake = 400 tokens with locking duration of 8 periods
			* 2nd sub-stake = 100 tokens locked starting from the next period and a locking duration of 5 periods
		- Next period, if winding down is disabled:  
			* 1st sub-stake = 400 tokens with locking duration of 8 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and a locking duration of 5 future periods
		- Next period, if winding down is enabled: 
			* 1st sub-stake = 400 tokens with locking duration of 7 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and a locking duration of 4 future periods

    .. code::

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
            + 0 + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9
		
			
			
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
            + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10        

			
			
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
            + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9        
