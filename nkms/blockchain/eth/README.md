# NuCypher KMS Ethereum

Ethereum (solidity) code for nucypher-kms, consists contracts and python classes for miners and clients.
Part of contracts was copied from [OpenZeppelin](https://github.com/OpenZeppelin/zeppelin-solidity) repo.
The basis is built on the [Populus](https://github.com/ethereum/populus) framework.


# Periods structure

Most of the function in contracts works by periods. For example, stake in the contract `Escrow` is discretely unlocked by periods.
Period is calculating using block.timestamp in getCurrentPeriod() function (`Miner.sol`). Each period is 24 hours. So result of getting locked tokens in one day will be the same.

# Main contracts

* Token contract
`NuCypherKMSToken` contract is ERC20 token with additional function - burn own tokens (only for owners)
* Miner contract  
`MinersEscrow` contract holds stake from miners, store information about miners activity and assigns a reward for participating in NuCypher KMS network
* Client contract  
`PolicyManager` contract holds policies fee and distributes fee by periods
* User escrow contract  
`UserEscrow` contract locks tokens for some time. In that period tokens are lineraly unlocked and all tokens can be used as stake in `MinersEscrow` contract

# Solidity libraries

* `LinkedList` library is structure of linked list for address data type
* `Dispatcher` contract is proxy which used for updating versions of any contract. See [README.MD](nkms.blockchain.eth/project/contracts/proxy/README.MD)
