# NuCypher Ethereum Contracts


## Contract Listing

* `NuCypherToken` ERC20 token contract with additional function - burn own tokens (only for owners)
* `MinersEscrow` Holds Ursula's stake, stores information about Ursula's activity and assigns a reward for participating in the NuCypher network. The `Issuer` contract is part of the `MinersEscrow` and uses only to split code
* `PolicyManager` Holds a policy's fee and distributes fee by periods
* `Upgradeable` Base contract for upgrading (<nucypher.blockchain.eth/project/contracts/proxy/README.MD>)
* `Dispatcher` Proxy to other contracts. This provides upgrading of the `MinersEscrow` and `PolicyManager` contracts
* `UserEscrow` Locks tokens for predetermined time. Tokens will be unlocked after specified time and all tokens can be used as a stake in the `MinersEscrow` contract

## Deployment Procedure

1. Deploy `NuCypherToken` with all future supply tokens
2. Deploy `MinersEscrow` with a dispatcher targeting it
3. Deploy `PolicyManager` with its own dispatcher, also targeting it
4. Transfer reward tokens to the `MinersEscrow` contract. These tokens are future mining rewards, and initial supply
5. Run the `initialize()` method to initialize the `MinersEscrow` contract
6. Set the address of the `PolicyManager` contract  in the `MinersEscrow` by using the `setPolicyManager(address)`
7. Pre-deposit tokens to the `MinersEscrow` if necessary:
	* Approve the transfer tokens for the `MinersEscrow` contract using the `approve(address, uint)` method. The parameters are the address of `MinersEscrow` and the amount of tokens for a miner or group of miners;
	* Deposit tokens to the `MinersEscrow` contract using the `preDeposit(address[], uint[], uint[])` method. The parameters are the addresses of token miner, the amount of tokens for each miner and the periods during which tokens will be locked for each miner
8. `UserEscrowLibraryLinker`, `UserEscrowProxy` TBD
9. Pre-deposit tokens to the `UserEscrow` if necessary:
	* Create new instance of the `UserEscrow` contract 
	* Transfer ownership of the instance of the `UserEscrow` contract to the user
	* Approve the transfer of tokens for the `UserEscrow`
	* Deposit tokens by the `initialDeposit(uint256, uint256)` method

## Alice's Contract Interaction

### Alice Authors a Blockchain Policy

Alice uses a network of Ursula miners to deploy policies.
In order to take advantage of the network, Alice chooses miners and deploys policies with fees for those miners.
Alice can choose miners by herself ("handpicked") or by using `findCumSum(uint256, uint256, uint256)` method of the contract `MinersEscrow` ("sampling").
`findCumSum` parameters are:
    * The start index (if the method is not called the first time)
    * The delta of the step
    * minimum number of periods during which tokens are locked.
This method will return only active miners.

In order to place the fee for a policy, Alice calls the method `PolicyManager.createPolicy(bytes20, uint256, uint256, address[])`;
By specifying a miner address, the policy ID (off-chain generation), the policy duration in periods, and the first period's reward.
Payment should be added to the transaction in ETH and the amount is `firstReward * miners.length + rewardRate * periods * miners.length`.
The reward rate must be greater than or equal to the minimum reward for each miner in the list. The first period's reward is not refundable, and can be zero.

### Alice Revokes a Blockchain Policy

When Alice wants to revoke a policy, she calls the `PolicyManager.revokePolicy(bytes20)` or `PolicyManager.revokeArrangement(bytes20, address)`.
Execution of these methods results in Alice recovering all fees for future periods, and also for periods when the miners were inactive.
Alice can refund ETH for any inactive miners periods without revoking the policy by using methods `PolicyManager.refund(bytes20)` or `PolicyManager.refund(bytes20, address)`.


## Ursula's Contract Interaction


### Ursula Locks Tokens

In order to become a participant of the network, a miner stakes tokens in the `MinersEscrow` contract.
The miner allows the (mining) contract to perform a transaction using the `MinersEscrow.approve(address, uint256)` method
(ERC20 contracts allow access delegation to another address).

After that, the miner transfers some quantity of tokens (`MinersEscrow.deposit(uint256, uint256)`), locking them at the same time.
Alternately the `NucypherToken.approveAndCall(address, uint256, bytes)` method can be used.
The parameters are:
    * The address of the `MinersEscrow` contract,
    * The amount of staked tokens
    * The periods for locking (which are serialized into an array of bytes).

When staking tokens, the miner sets the number of periods the tokens will be locked, but it must be no less than some minimal locking time (30 periods).
In order to unlock tokens, the miner must be active during the time of locking (and confirm activity each period).
Each stake is represented by the amount of tokens locked, and the stake's duration in periods.
The miner can add a new stake using `MinersEscrow.deposit(uint256, uint256)` or `MinersEscrow.lock(uint256, uint256)` methods.
The miner can split stake into two parts: one with the same duration and another with an extended duration.
For this purpose, the `MinersEscrow.divideStake(uint256, uint256, uint256, uint256)` method is used.
The first two parameters are used to identify the stake to divide and the last two for the extended part of the stake.
When calculating locked tokens (`MinersEscrow.getLockedTokens(address, uint256)` method), all stakes that are active during the specified period are summed.


### Ursula Confirms Activity

In order to confirm activity every period, miners call `MinersEscrow.confirmActivity()` wherein activities for the next period are registered.
The method `MinersEscrow.confirmActivity` is called every time the methods `MinersEscrow.deposit(uint256, uint256)` or `MinersEscrow.lock(uint256, uint256)` is called.
The miner gets a reward for every confirmed period.

### Ursula Generates Staking Rewards
After the period of activity has passed, the miner may call `MinersEscrow.mint()` method which computes and transfers tokens to the miner's account.
Also note that calls to `MinersEscrow.lock(uint256, uint256)` and `MinersEscrow.confirmActivity()` are included the `MinersEscrow.mint()` method.

The reward value depends on the fraction of locked tokens for the period (only those who confirmed activity are accounted for).
Also, the reward depends on the number of periods during which the tokens will be locked: if the tokens will be locked for half a year, the coefficient is 1.5.
The minimum coefficient is 1 (when tokens will get unlocked in the next period), and the maximum is 2 (when the time is 1 year or more).
The reward is calculated separately for each stake that is active during the mining period and all rewards are summed up.
The order of calling `mint` by miners (e.g. who calls first, second etc) doesn't matter.
Miners can claim their rewards by using the `witdraw(uint256)` method. Only non-locked tokens can be withdrawn.


### Ursula Generates Policy Rewards
Also the miner gets rewards for policies deployed.
Computation of the reward happens every time `mint()` is called by the `updateReward(address, uint256)` method.
In order to take the reward, the miner needs to call method `withdraw()` of the contract `PolicyManager`.
The miner can set a minimum reward rate for a policy. For that, the miner should call the `setMinRewardRate(uint256)` method.


### NuCypher Partner Ursula Staking
Some users will have locked but not staked tokens.
In that case, an instance of the `UserEscrow` contract will hold their tokens (method `initialDeposit(uint256, uint256)`).
All tokens will be unlocked after a specified time and the user can get them by method `withdraw(uint256)`.
When the user wants to become a miner - he uses the `UserEscrow` contract as a proxy for the `MinersEscrow` and `PolicyManager` contracts.
