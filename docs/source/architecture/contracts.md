# NuCypher Ethereum Contracts


## Contract Listing

* `NuCypherToken` ERC20 token contract
* `StakingEscrow` Holds Ursula's stake, stores information about Ursula's activity, and assigns a reward for participating in the NuCypher network. (The `Issuer` contract is part of the `StakingEscrow`)
* `PolicyManager` Holds a policy's fee and distributes fee by periods
* `Adjudicator` Manages [the slashing protocol](/architecture/slashing)
* `WorkLock` Manages token distribution
* `Upgradeable` Base contract for [upgrading](/architecture/upgradeable_proxy_contracts)
* `Dispatcher` Proxy to other contracts and provides upgrading of the `StakingEscrow`, `PolicyManager` and `Adjudicator` contracts
* `PreallocationEscrow` Locks tokens for some predetermined time. Tokens will be unlocked after the specified time and all tokens can be used as stake in the `StakingEscrow` contract

## Deployment Procedure

This section provides a step-by-step guide of how NuCypher contracts are deployed.
For a guide of how to deploy these contracts automatically, see the [Deployment guide](/guides/deployment_guide).

1. Deploy `NuCypherToken` with all future supply tokens
2. Deploy `StakingEscrow` with a dispatcher targeting it
3. Deploy `PolicyManager` with its own dispatcher, also targeting it
4. Deploy `Adjudicator` with a dispatcher
5. Deploy `StakingInterface` with `StakingInterfaceRouter` targeting it
6. Deploy `WorkLock` contract
7. Set the address of the `PolicyManager` contract  in the `StakingEscrow` by using the `setPolicyManager(address)`
8. Set the address of the `Adjudicator` contract  in the `StakingEscrow` by using the `setAdjudicator(address)`
9. Set the address of the `WorkLock` contract  in the `StakingEscrow` by using the `setWorkLock(address)`
10. Approve tokens transfer to the `StakingEscrow` contract. These tokens are future mining rewards
11. Run the `initialize(uint256)` method to initialize the `StakingEscrow` contract
12. Approve tokens transfer for distribution to the `WorkLock` contract and call `tokenDeposit(uint256)` method
13. Pre-deposit tokens to the `PreallocationEscrow`:
	* Create new instance of the `PreallocationEscrow` contract 
	* Transfer ownership of the instance of the `PreallocationEscrow` contract to the user
	* Approve the transfer of tokens for the `PreallocationEscrow`
	* Deposit tokens by the `initialDeposit(uint256, uint256)` method

## Alice's Contract Interaction

### Alice Authors a Blockchain Policy

Alice uses a network of Ursula stakers to deploy policies.
In order to take advantage of the network, Alice chooses stakers and deploys policies with fees for those stakers.
Alice can choose stakers by herself ("handpicked") or select from the result of `StakingEscrow.getActiveStakers(uint16, uint256, uint256)` method - This is  known as ("sampling").
`getActiveStakers` parameters are:
* Minimum number of periods during which tokens are locked
* Start index for looking in stakers array 
* Max stakers for looking
This method will return only active stakers.

In order to place the fee for a policy, Alice calls the method `PolicyManager.createPolicy(bytes16, address, uint64, address[])`,
specifying the staker's addresses, the policy ID (off-chain generation), the policy owner (could be zero address), and the end timestamp of the policy.
Payment should be added to the transaction in ETH and the amount is `rewardRate * periods * stakers.length`, where `periods` is `endTimestampPeriod - currentPeriod + 1`.
The reward rate must be greater than or equal to the minimum reward for each staker in the list.

### Alice Revokes a Blockchain Policy

When Alice wants to revoke a policy, she calls the `PolicyManager.revokePolicy(bytes16)` or `PolicyManager.revokeArrangement(bytes16, address)`.
Execution of these methods results in Alice recovering all fees for future periods, and also for periods when the stakers were inactive.
Alice can refund ETH for any inactive periods without revoking the policy by using the method `PolicyManager.refund(bytes16)` or `PolicyManager.refund(bytes16, address)`.
If Alice doesn't have ability to execute on-chain transaction or wants to share ability to revoke then she can sign revocation parameters. Anyone who have this signature will be able to revoke policy using `PolicyManager.revoke(bytes16, address, bytes)`


## Staker's Contract Interaction


### Staker Locks Tokens

In order to become a participant of the network, a staker stakes tokens in the `StakingEscrow` contract.
The staker allows the (staking) contract to perform a transaction using the `NuCypherToken.approve(address, uint256)` method
(ERC20 contracts allow access delegation to another address).

After that, the staker transfers some quantity of tokens (`StakingEscrow.deposit(uint256, uint16)`), locking them at the same time.
Alternately the `NucypherToken.approveAndCall(address, uint256, bytes)` method can be used.
The parameters are:
* The address of the `StakingEscrow` contract
* The amount of staked tokens
* The periods for locking (which are serialized into an array of bytes)

When staking tokens, the staker sets the number of periods the tokens will be locked, which must be no less than some minimal locking time (30 periods).
In order to unlock tokens, the staker must be active during the time of locking (and confirm activity each period).
Each stake is represented by the amount of tokens locked, and the stake's duration in periods.
The staker can add a new stake using `StakingEscrow.deposit(uint256, uint16)` or `StakingEscrow.lock(uint256, uint16)` methods.
The staker can split stake into two parts: one with the same duration and another with an extended duration.
For this purpose, the `StakingEscrow.divideStake(uint256, uint256, uint16)` method is used.
The first parameter is used to identify the stake to divide and the last two for the extended part of the stake.
When calculating locked tokens using the `StakingEscrow.getLockedTokens(address, uint16)` method, all stakes that are active during the specified period are summed.


### The Staker Bonds to a Worker ("Ursula")
The staker must specify a worker who will confirm the activity and sign on behalf of this staker by calling the `StakingEscrow.setWorker(address)` method.
Changing a worker is allowed no more than once within `StakingEscrow.minWorkerPeriods()`.
Only the worker can confirm activity.


### Ursula Confirms Activity

In order to confirm activity every period, workers call `StakingEscrow.confirmActivity()` wherein activities for the next period are registered.
The staker gets a reward for every confirmed period.

### Ursula Generates Staking Rewards
After the period of activity has passed, the staker may call `StakingEscrow.mint()` method which computes and transfers tokens to the staker's account.
Also note that calls to `StakingEscrow.confirmActivity()` are included the `StakingEscrow.mint()` method.

The reward value depends on the fraction of locked tokens for the period (only those who confirmed activity are accounted for).
Also, the reward depends on the number of periods during which the tokens will be locked: if the tokens will be locked for half a year, the coefficient is 1.5.
The minimum coefficient is 1 (when tokens will get unlocked in the next period), and the maximum is 2 (when the time is 1 year or more).
The reward is calculated separately for each stake that is active during the mining period and all rewards are summed up.
The order of calling `StakingEscrow.mint()` by stakers (e.g. who calls first, second etc) doesn't matter.
Stakers can claim their rewards by using the `StakingEscrow.withdraw(uint256)` method. Only non-locked tokens can be withdrawn.


### Ursula Generates Policy Rewards
Also the staker gets rewards for policies deployed.
Computation of a policy reward happens every time `StakingEscrow.mint()` is called by the `PolicyManager.updateReward(address, uint16)` method.
In order to take the reward, the staker needs to call method `withdraw()` of the contract `PolicyManager`.
The staker can set a minimum reward rate for a policy. For that, the staker should call the `PolicyManager.setMinRewardRate(uint256)` method.


### NuCypher Partner Ursula Staking
Some users will have locked but not staked tokens.
In that case, an instance of the `PreallocationEscrow` contract will hold their tokens (method `PreallocationEscrow.initialDeposit(uint256, uint256)`).
All tokens will be unlocked after a specified time and the user can retrieve them using the `PreallocationEscrow.withdrawTokens(uint256)` method.
When the user wants to become a staker - they use the `PreallocationEscrow` contract as a proxy for the `StakingEscrow` and `PolicyManager` contracts.


## Contracts Versioning
Upgradeable contracts, such as `Adjudicator`, `StakingEscrow`, `PolicyManager` and `StakingInterface`, have their version specified in contract doc inside @dev.  
Version format is `|vi.j.k|`, where `i` - major version, `j` - minor version, `k` - patch, for example `|v1.2.3|`:  
* Different major versions mean different forks and they are not upgradeable
* Minor versions relate to any signatures or state changes inside contract, contracts are upgradeable between minor versions, but have different ABI and follows different agent layers 
* Patches involve changes inside function(s) with signature(s) untouched. All patches with a common minor version can be upgraded from one to another without other changes
