Alice
========================
Alice uses the net of miners to deploy policies. 
In order to take advantage of network Alice should choose miners and deploy policies with fees for that miners.
Alice can choose miners by herself or by `findCumSum(uint256, uint256, uint256)` method of the contract `MinersEscrow`. 
The parameters are the start index (if the method is not called the first time), delta of the step and minimum number of periods during which tokens are locked.
This method will return only active miners.

In order to place fee for policy Alice should call method `createPolicy(bytes20, uint256, uint256, address[])` of the contract `PolicyManager` 
by specifying the miners addresses, the policy id (off-chain generation), duration in periods, first period reward.
Payment should be added in transaction in ETH and the amount is `firstReward * miners.length + rewardRate * periods * miners.length`.
Reward rate must be equal or more than minimum reward for each miner in the list. First period reward can not be refundable and it can be zero.

In case Alice wants to cancel policy then she calls the `revokePolicy(bytes20)` or `revokeArrangement(bytes20, address)` methods of the contract `PolicyManager`. 
While executing those methods Alice get all fee for future periods and for periods when the miners were inactive. 
Also Alice can refund ETH for inactive miners periods without revoking policy by using methods `refund(bytes20)` or `refund(bytes20, address)` of the contract `PolicyManager`.


Ursula
========================
In order to become a participant of the network, a miner stakes tokens in the `MinersEscrow` contract. 
The miner allows the (mining) contract to perform a transaction using the `approve(address, uint256)` method in the token contract 
(ERC20 contracts allow to delegrate access to another address). 
After that, the miner transfers some quantity of tokens (method `deposit(uint256, uint256)`), locking them at the same time. 
Another way to do it is using the `approveAndCall(address, uint256, bytes)` method in the token contract. 
The parameters are the address of the `MinersEscrow` contract, the amount of staked tokens and the periods for locking which are serialized into an array of bytes.

When staking tokens, the miner sets the number of periods while tokens will be locked, but it should be no less than some minimal locking time (30 periods).
In order to unlock tokens, the miner should be active during the time of locking (confirm activity).
Each stake is the amount of tokens and the duration in periods.
The miner can add new stake by the `deposit(uint256, uint256)` or `lock(uint256, uint256)` methods.
Also the miner can split stake into two parts: one with the same duration and other with an extended duration.
For this purpose, the `divideStake(uint256, uint256, uint256, uint256)` method is used.
The first two parameters are used to identify the stake to divide and the others two for the extended part of the stake.
When calculating locked tokens (`getLockedTokens(address, uint256)` method), all stakes that are active during the specified period are summed up.

In order to confirm activity every period, the miner should call `confirmActivity()` in the process of which activity for the next period is registered. 
Also the method `confirmActivity` is called every time when methods `deposit(uint256, uint256)` or `lock(uint256, uint256)` are called. 
The miner gets a reward for every confirmed period. 
After the period of activity has passed, the miner could call `mint()` method which computes and transfers tokens to the miner's account.
Also, the `lock(uint256, uint256)` and `confirmActivity()` methods include the `mint()` method.

The reward depends on the fraction of locked tokens for the period (only those who confirmed activity are accounted for)
Also, the reward depends on the number of periods during which the tokens will be locked: if the tokens will be locked in half a year, the coefficient is 1.5. 
Minimal coefficient is 1 (when tokens will get unlocked in the next period), and maximum is 2 (when the time is 1 year or more).
The reward is calculated separately for each stakes that are active during the mining period and all rewards are summed up.
The order of calling `mint` by miners (e.g. who calls first, second etc) doesn't matter. 
All reward the miner can get by using the `witdraw(uint256)` method. Only non-locked tokens can be withdrawn.

Also the miner gets rewards for policies deployed. 
Computation of the reward happens every time `mint()` is called by the `updateReward(address, uint256)` method. 
In order to take the reward, the miner needs to call method `withdraw()` of the contract `PolicyManager`.
The miner can set a minimum reward rate for a policy. For that, the miner should call the `setMinRewardRate(uint256)` method.

Some users will have locked but not staked tokens. 
In that case, a instance of the `UserEscrow` contract will hold their tokens (method `initialDeposit(uint256, uint256)`).
All tokens will be unlocked after specified time and the user can get them by method `withdraw(uint256)`.
When the user wants to become a miner - he uses the `UserEscrow` contract as a proxy for the `MinersEscrow` and `PolicyManager` contracts.
