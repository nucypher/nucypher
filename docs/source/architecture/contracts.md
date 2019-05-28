# Nucypher Ethereum Contracts


## Contract Listing

* `NuCypherToken` ERC20 token contract
* `StakingEscrow` Holds Ursula's stake, stores information about Ursula's activity, and assigns a reward for participating in the NuCypher network. (The `Issuer` contract is part of the `StakingEscrow`)
* `PolicyManager` Holds a policy's fee and distributes fee by periods
* `Adjudicator` Manages [the slashing protocol](slashing)
* `Upgradeable` Base contract for [upgrading](upgradeable_proxy_contracts)
* `Dispatcher` Proxy to other contracts and provides upgrading of the `StakingEscrow`, `PolicyManager` and `Adjudicator` contracts
* `UserEscrow` Locks tokens for predetermined time. Tokens will be unlocked after specified time and all tokens can be used as stake in the `StakingEscrow` contract

## Deployment Procedure

1. Deploy `NuCypherToken` with all future supply tokens
2. Deploy `StakingEscrow` with a dispatcher targeting it
3. Deploy `PolicyManager` with its own dispatcher, also targeting it
4. Deploy `Adjudicator` with a dispatcher
5. Transfer reward tokens to the `StakingEscrow` contract. These tokens are future mining rewards and initial allocations
6. Run the `initialize()` method to initialize the `StakingEscrow` contract
7. Set the address of the `PolicyManager` contract  in the `StakingEscrow` by using the `setPolicyManager(address)`
8. Pre-deposit tokens to the `StakingEscrow` if necessary:
	* Approve the transfer tokens for the `StakingEscrow` contract using the `approve(address, uint)` method. The parameters are the address of `StakingEscrow` and the amount of tokens for a staker or group of stakers;
	* Deposit tokens to the `StakingEscrow` contract using the `preDeposit(address[], uint[], uint[])` method. The parameters are the addresses of the stakers, the amount of tokens for each staker, and the number of periods during which tokens will be locked for each staker
9. Deploy `UserEscrowProxy` with `UserEscrowLibraryLinker` targeting it
10. Pre-deposit tokens to the `UserEscrow` and, if necessary:
	* Create new instance of the `UserEscrow` contract 
	* Transfer ownership of the instance of the `UserEscrow` contract to the user
	* Approve the transfer of tokens for the `UserEscrow`
	* Deposit tokens by the `initialDeposit(uint256, uint256)` method

## Alice's Contract Interaction

### Alice Authors a Blockchain Policy

Alice uses a network of Ursula stakers to deploy policies.
In order to take advantage of the network, Alice chooses stakers and deploys policies with fees for those stakers.
Alice can choose stakers by herself ("handpicked") or by using `StakingEscrow.sample(uint256[], uint16)` - This is  known as ("sampling").
`sample` parameters are:
* The array of absolute values
* Minimum number of periods during which tokens are locked
This method will return only active stakers.

In order to place the fee for a policy, Alice calls the method `PolicyManager.createPolicy(bytes16, uint16, uint256, address[])`,
specifying the staker's addresses, the policy ID (off-chain generation), the policy duration in periods, and the first period's reward.
Payment should be added to the transaction in ETH and the amount is `firstReward * stakers.length + rewardRate * periods * stakers.length`.
The reward rate must be greater than or equal to the minimum reward for each staker in the list. The first period's reward is not refundable, and can be zero.

### Alice Revokes a Blockchain Policy

When Alice wants to revoke a policy, she calls the `PolicyManager.revokePolicy(bytes16)` or `PolicyManager.revokeArrangement(bytes16, address)`.
Execution of these methods results in Alice recovering all fees for future periods, and also for periods when the stakers were inactive.
Alice can refund ETH for any inactive periods without revoking the policy by using the method `PolicyManager.refund(bytes16)` or `PolicyManager.refund(bytes16, address)`.


## Ursula's Contract Interaction


### Ursula Locks Tokens

In order to become a participant of the network, a staker stakes tokens in the `StakingEscrow` contract.
The staker allows the (mining) contract to perform a transaction using the `NuCypherToken.approve(address, uint256)` method
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


### Ursula Confirms Activity

In order to confirm activity every period, stakers call `StakingEscrow.confirmActivity()` wherein activities for the next period are registered.
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
In that case, an instance of the `UserEscrow` contract will hold their tokens (method `UserEscrow.initialDeposit(uint256, uint256)`).
All tokens will be unlocked after a specified time and the user can retrieve them using the `UserEscrow.withdraw(uint256)` method.
When the user wants to become a staker - he uses the `UserEscrow` contract as a proxy for the `StakingEscrow` and `PolicyManager` contracts.


### Ursula's Worker
In the case when Ursula uses an intermediary contract to lock tokens (for example, `UserEscrow`), the staker must specify a worker who will confirm the activity and sign on behalf of this staker by calling the `StakingEscrow.setWorker(address)` method.
Changing a worker is allowed no more than 1 time in `StakingEscrow.minWorkerPeriods()`.
Only the worker can confirm activity (by default, the worker is the staker).
