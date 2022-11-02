# Registries of NuCypher Networks

This directory contains an authoritative source of contract registries for several NuCypher networks.
These registries comprise the official addresses and ABIs for the networks' smart contracts.


## Current deployments

* `mainnet`: The main NuCypher Network, offering cryptographic runtimes for secrets management and dynamic access control 🚀
  * [**NuCypherToken**](https://etherscan.io/address/0x4fE83213D56308330EC302a8BD641f1d0113A4Cc): `0x4fE83213D56308330EC302a8BD641f1d0113A4Cc`
  * [**StakingEscrow (Dispatcher)**](https://etherscan.io/address/0xbbD3C0C794F40c4f993B03F65343aCC6fcfCb2e2): `0xbbD3C0C794F40c4f993B03F65343aCC6fcfCb2e2`
  * [**PolicyManager (Dispatcher)**](https://etherscan.io/address/0x67E4A942c067Ff25cE7705B69C318cA2Dfa54D64): `0x67E4A942c067Ff25cE7705B69C318cA2Dfa54D64`
  * [**Adjudicator (Dispatcher)**](https://etherscan.io/address/0x359924Be0640659F34198e518BF3d40Fb56160BE): `0x359924Be0640659F34198e518BF3d40Fb56160BE`
  * [**WorkLock**](https://etherscan.io/address/0xe9778e69a961e64d3cdbb34cf6778281d34667c2): `0xe9778e69a961e64d3cdbb34cf6778281d34667c2`
  * [**SimplePREApplication**](https://etherscan.io/address/0x7E01c9c03FD3737294dbD7630a34845B0F70E5Dd): `0x7E01c9c03FD3737294dbD7630a34845B0F70E5Dd`
* `polygon-mainnet`: Used for cost-effective PRE subscription payments
  * [**SubscriptionManager**](https://polygonscan.com/address/0xB0194073421192F6Cf38d72c791Be8729721A0b3): `0xB0194073421192F6Cf38d72c791Be8729721A0b3`
* `polygon-mumbai`:
  * [**SubscriptionManager**](https://mumbai.polygonscan.com/address/0xb9015d7B35Ce7c81ddE38eF7136Baa3B1044f313): `0xb9015d7B35Ce7c81ddE38eF7136Baa3B1044f313`
* `tapir`: Public Long-Term Support testnet, intended as a stable playground for network users (Goerli) testnet.
  * [**TestnetThresholdStaking**](https://goerli.etherscan.io/address/0x09B5065d2924De33C85F76474A89A27189402064): `0x09B5065d2924De33C85F76474A89A27189402064`
  * [**SimplePREApplication**](https://goerli.etherscan.io/address/0xaF96aa6000ec2B6CF0Fe6B505B6C33fa246967Ca): `0xaF96aa6000ec2B6CF0Fe6B505B6C33fa246967Ca`
* `lynx`: Internal development testnet, chaotic, used for experimental code and staging. (Goerli). 
  * TBD 

## Historical deployments

The following is a list of networks that we used at some point in the past and that are currently deprecated:

* `miranda`: Our first decentralized testnet.
* `frances`: Our second testnet. Only for development purposes.
* `cassandra`: Incentivized Testnet, supporting our 'Come and Stake It' initiative.
* `gemini`: New version of Incentivized Testnet, supporting Phase 4 of 'Come and Stake It'.
* `ibex`: Public testnet, intended as a playground for stakers & node operators (e.g., learning how to create and manage stakes, setting up a node), as well as for internal development purposes. Running on Ethereun Rinkeby testnet.
* `oryx`: Staking testnet on Ropsten for initial threshold network integration
