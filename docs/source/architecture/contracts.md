NuCypher Ethereum Contracts
============================
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
