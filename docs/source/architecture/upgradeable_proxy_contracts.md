# Upgradeable Contracts

Smart contracts in Ethereum are not really changeable. Even it can not be deleted - contract still exists in blockchain after `selfdestruct` (only storage cleared).
So fixing bugs and upgrading logic is to change contract (address) and save previous storage values.
Simple way for this is to create new contract, then copy storage there and destruct (mark as deleted) old contract.
But in this case client should change address for requested contract and also while migration will be active two versions of contract.
More convenient way is to use proxy contract with interface where each method redirect to the target contract.
It's good option because client uses one address most of the time but also have some minus - when we should add some methods then need to change proxy address too.
Another way is using fallback function in proxy contract - this function will execute on any request, redirect request to target and return result value (using some opcodes).
Almost like previous option, but this proxy doesn't have interface methods, only fallback function, so no need to change proxy address if we should change methods.
This way is not ideal and has some restrictions (here only major):

* Sending Ether from client's account to contract uses fallback function. Such transaction could consume only 2300 gas (http://solidity.readthedocs.io/en/develop/contracts.html#fallback-function)
* Proxy contract (Dispatcher) holds storage (not in the contract itself). While upgrading storage values should be the same or equivalent (see below)

## Sources

More examples:
* https://github.com/maraoz/solidity-proxy - good realization of using libraries (not contracts) but too complex and some ideas is obsolete after Byzantium hard fork
* https://github.com/willjgriff/solidity-playground - most of the upgradeable code taken from this repository
* https://github.com/0v1se/contracts-upgradeable - almost the same but also have code for verifying upgrade

## Interaction scheme

![Interaction scheme](../.static/img/Dispatcher.png)

* Dispatcher - proxy contract that redirects requests to the target address.
Also it clearly holds own values (owner and target address) and stores the values of the target contract but not explicitly.
Client should use result contract or interface ABI while sending request to the Dispatcher address.
Owner can change target address by using Dispatcher ABI.
Dispatcher contract uses `delegatecall` for redirecting requests, so msg.sender remains client address and uses storage from dispatcher when executing method in target contract.
If target address is not set or target contract is not exists result may be unpredictable, because `delegatecall` will return true.

* Contract - upgradeable contract, each version should have same order of storage values.
New versions of contract can expand values, but must contain all old values (first of all should contain values from dispatcher).
This contract is like library because it's storage is not used.
If client send request to the contract without using dispatcher then request could be executed without exception
but using wrong target address (should be dispatcher address) and wrong storage (should be dispatcher storage).

## Development
* Use Upgradeable as base contract for all contracts that will be used with Dispatcher
* Implement `verifyState(address)` method which checks that new version has correct storage
* Implement `finishUpgrade(address)` method which should copy initialization data from library storage to the dispatcher storage
* Each upgrade should include tests which check storage equivalence


## Desired Properties

* Nodes decide which update should occur;
* Nodes can rollback contract if new version has bugs.

### Approaches

* "Hard-fork"
![Hard-fork](../.static/img/Hard-fork.png)

Each version is a new contract with separate address and storage.
Nodes should change contract address that they use.
    - Advantages:
        - Code is simpler, no special requirements;
        - Each node can choose which contract to use.
    - Disadvantages:
        - There are two versions of contract while updating, so contracts should work together.
        Also we can add another contract (Government) for voting and migration between versions.

* [Dispatcher](README.MD) (proxy)
![Dispatcher](../.static/img/Dispatcher2.png)

Using proxy contract that holds storage and library address.
Updating is changing only one library address in proxy contract.
    - Advantages:
        - Instant update without changing address for nodes.
    - Disadvantages:
        - Certain rules for updating the contract storage,
        better to write additional methods for testing contract storage;
        - A voting contract (Government) is required for a legitimate upgrade.

### Implementation

* "Hard-fork"
    *	Soft updating with two contracts
    ![Hard-fork-impl1](../.static/img/Hard-fork2.png)

    Updating contracts should contain methods for transfer data (amount of locked tokens, balance etc.).
    For example, change manager address from old to new in Wallet contract.
    Also both version should interact for correct mining
    (all locked blocks will be sum from old and new versions in the current period).
    For rollback will be enough to move data from the new version back to the previous.
    In some moment, new version have to disable previous contract and move remaining data to the new version.

    *	Full update from one contract to another
    ![Hard-fork-impl2](../.static/img/Hard-fork3.png)
    All nodes vote for updating using additional contract.
    After the end of voting old contract should be blocked and new version is activated (or created).
    And then data will be copied from old version to new, for example, by new contract.
    Rollback is almost the same: new version is paused,
    data is moved back to the old version and old version is activated.
    So main task is the addition of methods for obtaining data for old and new versions.

*	Dispatcher

![Dispatcher-impl](../.static/img/Dispatcher3.png)
After voting Government contract changes library address in proxy.
Rollback is changing address back from the new library to the old.
Main goal is create right voting and check storage while setting new address.
