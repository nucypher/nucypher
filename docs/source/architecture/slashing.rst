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

The punishment is to reduce the number of tokens that belongs to the offending staker.
In this case, the main task is not to violate the logic of locking tokens.
The whole stake consists of several parts:

* tokens which the staker can withdraw at any moment
* tokens locked for a specific period

Since a staker can divide a stake (extend a part of a stake), as well as lock new tokens, then the total stake is represented as the sum of all the sub stakes active at a particular period. Each sub stake has a beginning and duration, which is reduced only upon confirmation of the activity. Staker slashed on the principle: first a sub stake, which will end earlier. Therefore, in the first place, the not-locked part of tokens belonging to the staker is slashed. After that, if necessary, sub stakes are adjusted: finds the shortest sub stake and decreases by the required amount. If this is not enough, then the next short sub stake is searched for, and so on. A sub stake that begins in the next period is checked separately.

Example:

1000 tokens belong to the staker, 1st sub stake - 500 tokens are locked for 10 periods, 2nd sub stake - 200 tokens for 2 periods and 3rd sub stake - 100 tokens that are locked starting from the next period.

* Penalty 100 tokens. The parameters of sub stakes will not change. Only the number of tokens belonging to the staker will decrease from 1000 to 900. 
* Penalty 400 tokens. There will be 600 tokens belonging to the staker. At the same time, in the current period 700 tokens were locked, and in the next only 600. So to normalize stake distribution - the shortest sub stake (second) is reduced by 100 tokens, the remaining sub stakes remain unchanged
* Penalty 600 tokens. 400 tokens are remain. Reducing the shortest sub stake (second) is not enough, so it's removed. After the first sub stake is reduced from 500 to 400, and the third sub stake which starting in the next period is also removed.