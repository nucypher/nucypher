NuCypher contracts
========================
* `NuCypherToken` contract is the ERC20 token contract with additional function - burn own tokens (only for owners)
* `MinersEscrow` contract holds Ursula's stake, stores information about Ursulas activity and assigns a reward for participating in NuCypher network. The `Issuer` contract is part of the `MinersEscrow` and uses only to split code
* `PolicyManager` contract holds policies fee and distributes fee by periods
* `Upgradeable` is base contract for upgrading (<nucypher.blockchain.eth/project/contracts/proxy/README.MD>)
* `Dispatcher` contract is used as proxy to other contracts. This provides upgrading of the `MinersEscrow` and `PolicyManager` contracts
* `UserEscrow` contract locks tokens for some time. Tokens will be unlocked after specified time and all tokens can be used as a stake in the `MinersEscrow` contract

Deployment
========================
* The first place is the contract `NuCypherToken` with all future supply tokens
* Next `MinersEscrow` should be deployed with its dispatcher
* Similarly `PolicyManager` is deployed with own dispatcher
* Transfer reward tokens to the `MinersEscrow` contract. This tokens is reward for mining. The remaining tokens are initial supply
* Run the `initialize()` method to initialize the `MinersEscrow` contract
* Set the address of the `PolicyManager` contract  in the `MinersEscrow` by using the `setPolicyManager(address)`
* Pre-deposit tokens to the `MinersEscrow` if necessary:
	* Approve the transfer tokens for the `MinersEscrow` contract using the `approve(address, uint)` method. The parameters are the address of `MinersEscrow` and the amount of tokens for a miner or group of miner;
	* Deposit tokens to the `MinersEscrow` contract using the `preDeposit(address[], uint[], uint[])` method. The parameters are the addresses of token miner, the amount of token for each miner and the periods during which tokens will be locked for each miner
* `UserEscrowLibraryLinker`, `UserEscrowProxy` TBD
* Pre-deposit tokens to the `UserEscrow` if necessary:
	* Create new instance of the `UserEscrow` contract 
	* Transfer ownership of the instance of the `UserEscrow` contract to the user
	* Approve the transfer tokens for the `UserEscrow`
	* Deposit tokens by the `initialDeposit(uint256, uint256)` method

Miner / Ursula
========================
In order to become a participant of the network, a miner should stake tokens in the `MinersEscrow` contract. 
For that, the miner allows the (mining) contract to do a transaction using the `approve(address, uint256)` method in the token contract 
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

Upgrade
========================
Smart contracts in Ethereum are not really changeable. 
So fixing bugs and upgrading logic is to change the contract (address) and save the previous storage values.
The `Dispatcher` contract is used for this purpose - the fallback function in contract will execute on any request, 
redirect request to the target address (delegatecall) and return result value (using some opcodes).
A target contract should be inherited from the `Upgradeable` contract in addition to the use of the `Dispatcher`. 
The `Upgradeable` contract include 2 abstract methods that need to be implemented:
`verifyState(address)` method which checks that new version has correct storage;
`finishUpgrade(address)` method which should copy initialization data from library storage to the dispatcher storage;
