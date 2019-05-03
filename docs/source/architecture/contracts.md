# Nucypher Ethereum Contracts


## Contract Listing

* `NuCypherToken` ERC20 token contract
* `MinersEscrow` Holds Ursula's stake, stores information about Ursula's activity, and assigns a reward for participating in the NuCypher network. (The `Issuer` contract is part of the `MinersEscrow`)
* `PolicyManager` Holds a policy's fee and distributes fee by periods
* `MiningAdjudicator` Manages [the slashing protocol](slashing)
* `Upgradeable` Base contract for [upgrading](upgradeable_proxy_contracts)
* `Dispatcher` Proxy to other contracts and provides upgrading of the `MinersEscrow`, `PolicyManager` and `MiningAdjudicator` contracts
* `UserEscrow` Locks tokens for predetermined time. Tokens will be unlocked after specified time and all tokens can be used as stake in the `MinersEscrow` contract

## Deployment Procedure

1. Deploy `NuCypherToken` with all future supply tokens
2. Deploy `MinersEscrow` with a dispatcher targeting it
3. Deploy `PolicyManager` with its own dispatcher, also targeting it
4. Deploy `MiningAdjudicator` with a dispatcher
5. Transfer reward tokens to the `MinersEscrow` contract. These tokens are future mining rewards and initial allocations
6. Run the `initialize()` method to initialize the `MinersEscrow` contract
7. Set the address of the `PolicyManager` contract  in the `MinersEscrow` by using the `setPolicyManager(address)`
8. Pre-deposit tokens to the `MinersEscrow` if necessary:
	* Approve the transfer tokens for the `MinersEscrow` contract using the `approve(address, uint)` method. The parameters are the address of `MinersEscrow` and the amount of tokens for a miner or group of miners;
	* Deposit tokens to the `MinersEscrow` contract using the `preDeposit(address[], uint[], uint[])` method. The parameters are the addresses of the miners, the amount of tokens for each miner, and the number of periods during which tokens will be locked for each miner
9. Deploy `UserEscrowProxy` with `UserEscrowLibraryLinker` targeting it
10. Pre-deposit tokens to the `UserEscrow` and, if necessary:
	* Create new instance of the `UserEscrow` contract 
	* Transfer ownership of the instance of the `UserEscrow` contract to the user
	* Approve the transfer of tokens for the `UserEscrow`
	* Deposit tokens by the `initialDeposit(uint256, uint256)` method

## Alice's Contract Interaction

### Alice Authors a Blockchain Policy

Alice uses a network of Ursula miners to deploy policies.
In order to take advantage of the network, Alice chooses miners and deploys policies with fees for those miners.
Alice can choose miners by herself ("handpicked") or by using `MinersEscrow.sample(uint256[], uint16)` - This is  known as ("sampling").
`sample` parameters are:
* The array of absolute values
* Minimum number of periods during which tokens are locked
This method will return only active miners.

In order to place the fee for a policy, Alice calls the method `PolicyManager.createPolicy(bytes16, uint16, uint256, address[])`,
specifying the miner's addresses, the policy ID (off-chain generation), the policy duration in periods, and the first period's reward.
Payment should be added to the transaction in ETH and the amount is `firstReward * miners.length + rewardRate * periods * miners.length`.
The reward rate must be greater than or equal to the minimum reward for each miner in the list. The first period's reward is not refundable, and can be zero.

### Alice Revokes a Blockchain Policy

When Alice wants to revoke a policy, she calls the `PolicyManager.revokePolicy(bytes16)` or `PolicyManager.revokeArrangement(bytes16, address)`.
Execution of these methods results in Alice recovering all fees for future periods, and also for periods when the miners were inactive.
Alice can refund ETH for any inactive periods without revoking the policy by using the method `PolicyManager.refund(bytes16)` or `PolicyManager.refund(bytes16, address)`.


## Ursula's Contract Interaction


### Ursula Locks Tokens

In order to become a participant of the network, a miner stakes tokens in the `MinersEscrow` contract.
The miner allows the (mining) contract to perform a transaction using the `NuCypherToken.approve(address, uint256)` method
(ERC20 contracts allow access delegation to another address).

After that, the miner transfers some quantity of tokens (`MinersEscrow.deposit(uint256, uint16)`), locking them at the same time.
Alternately the `NucypherToken.approveAndCall(address, uint256, bytes)` method can be used.
The parameters are:
* The address of the `MinersEscrow` contract
* The amount of staked tokens
* The periods for locking (which are serialized into an array of bytes)

When staking tokens, the miner sets the number of periods the tokens will be locked, which must be no less than some minimal locking time (30 periods).
In order to unlock tokens, the miner must be active during the time of locking (and confirm activity each period).
Each stake is represented by the amount of tokens locked, and the stake's duration in periods.
The miner can add a new stake using `MinersEscrow.deposit(uint256, uint16)` or `MinersEscrow.lock(uint256, uint16)` methods.
The miner can split stake into two parts: one with the same duration and another with an extended duration.
For this purpose, the `MinersEscrow.divideStake(uint256, uint256, uint16)` method is used.
The first parameter is used to identify the stake to divide and the last two for the extended part of the stake.
When calculating locked tokens using the `MinersEscrow.getLockedTokens(address, uint16)` method, all stakes that are active during the specified period are summed.


### Ursula Confirms Activity

In order to confirm activity every period, miners call `MinersEscrow.confirmActivity()` wherein activities for the next period are registered.
The miner gets a reward for every confirmed period.

### Ursula Generates Staking Rewards
After the period of activity has passed, the miner may call `MinersEscrow.mint()` method which computes and transfers tokens to the miner's account.
Also note that calls to `MinersEscrow.confirmActivity()` are included the `MinersEscrow.mint()` method.

The reward value depends on the fraction of locked tokens for the period (only those who confirmed activity are accounted for).
Also, the reward depends on the number of periods during which the tokens will be locked: if the tokens will be locked for half a year, the coefficient is 1.5.
The minimum coefficient is 1 (when tokens will get unlocked in the next period), and the maximum is 2 (when the time is 1 year or more).
The reward is calculated separately for each stake that is active during the mining period and all rewards are summed up.
The order of calling `MinersEscrow.mint()` by miners (e.g. who calls first, second etc) doesn't matter.
Miners can claim their rewards by using the `MinersEscrow.withdraw(uint256)` method. Only non-locked tokens can be withdrawn.


### Ursula Generates Policy Rewards
Also the miner gets rewards for policies deployed.
Computation of a policy reward happens every time `MinersEscrow.mint()` is called by the `PolicyManager.updateReward(address, uint16)` method.
In order to take the reward, the miner needs to call method `withdraw()` of the contract `PolicyManager`.
The miner can set a minimum reward rate for a policy. For that, the miner should call the `PolicyManager.setMinRewardRate(uint256)` method.


### NuCypher Partner Ursula Staking
Some users will have locked but not staked tokens.
In that case, an instance of the `UserEscrow` contract will hold their tokens (method `UserEscrow.initialDeposit(uint256, uint256)`).
All tokens will be unlocked after a specified time and the user can retrieve them using the `UserEscrow.withdraw(uint256)` method.
When the user wants to become a miner - he uses the `UserEscrow` contract as a proxy for the `MinersEscrow` and `PolicyManager` contracts.


### Ursula's Worker
In the case when Ursula uses an intermediary contract to lock tokens (for example, `UserEscrow`), the staker must specify a worker who will confirm the activity and sign on behalf of this staker by calling the `MinersEscrow.setWorker(address)` method.
Changing a worker is allowed no more than 1 time in `MinersEscrow.minWorkerPeriods()`.
Only the worker can confirm activity (by default, the worker is the staker).
