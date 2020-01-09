Sub-stakes
==========

A staker may extend the unlock period for any number of portions of their total stake. This divides the stake into smaller parts, each with a unique unlock date in the future. Stakers may also acquire and lock new tokens. The total stake is represented as the sum of all the different sub-stakes active in a given cycle (new cycle every 24h), which includes locked sub-stakes, and any sub-stakes that have passed their unlock date, and can be freely withdrawn. Each sub-stake has a beginning and duration (lock time). When a staker confirms activity each day and winding down is enabled, the remaining lock time for relevant sub-stakes is reduced.

Sub-stake remains active until become unlocked and staker get reward for last period of sub-stake by calling ``mint()`` or ``confirmActivity()`` after the last period is surpassed. Each staker can have no more than 30 active sub-stakes. All sub-stakes changes use slots of inactive sub-stakes in the first place and only after that - empty slots in the array. Therefore, obtaining data on past staker locks is not guaranteed.



Operations that modify the sub-stake array
------------------------------------------

Deposit and locking
^^^^^^^^^^^^^^^^^^^
*Methods* : ``deposit(uint256,uint16)``,  ``deposit(address,uint256,uint16)``,  ``lock(uint256,uint16)``

To become a staker, tokens owner transfers tokens to ``StakingEscrow`` and lock them  using one of the ``deposit()`` methods. In case that staker already has some amount of unlocked tokens on the account in the contract then lock can be created using ``lock()`` method. As a result of executing on of the above methods, a new element will be created in the array of sub-stakes with the next period as starting date  and with duration equals input parameter.


**Example:**

    A staker deposits 900 tokens:
        * 1st sub-stake = 900 tokens starting from the next period and locked for 5 periods

    .. aafig::
        :proportional:
        :textual:

            stake
            ^
            |
         900|   +-------------+
            |   |     1st     |  period
            +---+-------------+--->
            0   1             5



Lock prolongation
^^^^^^^^^^^^^^^^^
*Methods* : ``prolongStake(uint256,uint16)``

In order to increase the staking reward, as well as the possibility of obtaining policies with a longer time,  staker can increase the locking duration of the sub-stake using the ``prolongStake()`` method. The number of sub-stakes does not change, but the end period of locking in the specified sub-stake will be changed.

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
         900+----------+          
            |    1st   |  period
            +----------+--->   
            0          5          
			
			
			
                 After             

            stake                 
            ^                     
            |                     
         900+-------------+        
            |      1st    |  period
            +-------------+--->   
            0             7     
			
			
Sub-stake division
^^^^^^^^^^^^^^^^^^
*Methods* : ``divideStake(uint256,uint256,uint16)``

If necessary, staker can extend the locking duration only for the part of tokens in a sub-stake (``divideStake()``). Contract method splits desirable sub-stake into two elements: the old sub-stake with changed locked amount and the new sub-stake. New element has the extended locking duration (by the specified number of periods) and the same start period as the old one has. Locked amount in the new sub-stake equals to requested input parameter.

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
         900+----------+          
            |          |  
            |    1st   |
            |          |  period 
            +----------+--->   
            0          5          
			
			
			
                 After             

            stake                 
            ^                     
            |                     
         900+----------+       
            |          |
            |    1st   |
         300+----------+--+
            |      2nd    |  period
            +-------------+--->   
            0          5  7     


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
In case when re-staking parameter is on then all staking reward is locked as the part of each involved sub-stake (inside ``confirmActivity()`` and/or ``mint()``).  Accordingly, each such sub-stake has increased locked amount (by reward) and the number of sub-stakes stays unchanged.

**Example:**

    A staker has few sub-stakes and calls ``mint()``:
		- Before calling: 
			* 1st sub-stake = 400 tokens for 10 periods
			* 2nd sub-stake = 200 tokens for 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
			* 100 tokens in an unlocked state
		- After calling, re-staking is disabled:  
			* 1st sub-stake = 400 tokens for 10 periods
			* 2nd sub-stake = 200 tokens for 2 periods
			* 3rd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
			* 170 tokens in an unlocked state
		- After calling, re-staking is enabled: 
			* 1st sub-stake = 450 tokens for 10 periods
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
         700|     +----+
            |     | 3rd|
         600+-----+----+
         500|          +-------------+
            |    2nd   |     3rd     |
         400+----------+-------------+----------+
            |                                   |
            |               1st                 |   period
            +-----------------------------------+--->    
            0     1    2             5          10
			
			
                 After, re–staking is enabled             

            stake
            ^
            |
         770|     +----+
            |     | 3rd|
         670+-----+----+
            |          |
         550|    2nd   +-------------+
            |          |     3rd     |
         450+----------+-------------+----------+
            |                                   |
            |               1st                 |
            |                                   |   period
            +-----------------------------------+--->    
            0     1    2             5          10
			

Winding down
^^^^^^^^^^^^
*Used in methods* : ``confirmActivity()``

Disabled winding down parameter (by default) guarantees that worker must call ``confirmActivity()`` at least N times after parameter will be turned on to unlock sub-stake, where N is locking duration of sub-stake. Thus unlocking date for each sub-stakes shifts by 1 period each period (duration remains the same). In case when winding down is enabled, each ``confirmActivity()`` (no more than once in a period) leads to decreasing of locking duration of each sub-stake. If worker calls ``confirmActivity()`` each period then unlocking date remains unchanged.

**Example:**

    A staker has few sub-stakes, worker calls ``сonfirmActivity()`` each period:
		- Current period: 
			* 1st sub-stake = 400 tokens for 10 periods
			* 2nd sub-stake = 100 tokens locked starting from the next period and locked for 5 periods
		- Next period, winding down is disabled:  
			* 1st sub-stake = 400 tokens for 10 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and locked for 5 future periods
		- Next period, winding down is enabled: 
			* 1st sub-stake = 400 tokens for 9 periods
			* 2nd sub-stake = 100 tokens locked starting from the current period and locked for 4 future periods

    .. aafig::
        :proportional:
        :textual:
			
                 Current period           

            stake
            ^
            |
         500|  +---------+
            |  |   2nd   |
         400+--+---------+----------+
            |                       |
            |         1st           |
            |                       |   period
            +-----------------------+--->    
            0  1         5          10
			
			
                 Next period, winding down is disabled           

            stake
            ^
            |
         500+------------+
            |     2nd    |
         400+------------+----------+
            |                       |
            |         1st           |
            |                       |   period
            +-----------------------+--->    
            1            6          11
			
			
                 Next period, winding down is enabled           

            stake
            ^
            |
         500+----------+
            |    2nd   |
         400+----------+----------+
            |                     |
            |         1st         |
            |                     |     period
            +---------------------+----->    
            1          5          10