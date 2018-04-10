# Desired properties:
* Nodes decide which update should occur;
* Nodes can rollback contract if new version has bugs.
# Approaches
* "Hard-fork"  
![Hard-fork](pics/Hard-fork.png)  
Each version is a new contract with separate address and storage.
Nodes should change contract address that they use.
    - Advantages:
        - Code is simpler, no special requirements;
        - Each node can choose which contract to use.
    - Disadvantages:
        - There are two versions of contract while updating, so contracts should work together.
        Also we can add another contract (Government) for voting and migration between versions.
* [Dispatcher](README.MD) (proxy)  
![Dispatcher](pics/Dispatcher2.png)  
Using proxy contract that holds storage and library address.
Updating is changing only one library address in proxy contract.
    - Advantages:
        - Instant update without changing address for nodes.
    - Disadvantages:
        - Certain rules for updating the contract storage,
        better to write additional methods for testing contract storage;
        - A voting contract (Government) is required for a legitimate upgrade.
# Implementation
* "Hard-fork"
    *	Soft updating with two contracts  
![Hard-fork-impl1](pics/Hard-fork2.png)  
Updating contracts should contain methods for transfer data (amount of locked tokens, balance etc.).
For example, change manager address from old to new in Wallet contract.
Also both version should interact for correct mining
(all locked blocks will be sum from old and new versions in the current period).
For rollback will be enough to move data from the new version back to the previous.
In some moment, new version have to disable previous contract and move remaining data to the new version.  
    *	Full update from one contract to another  
![Hard-fork-impl2](pics/Hard-fork3.png)  
All nodes vote for updating using additional contract.
After the end of voting old contract should be blocked and new version is activated (or created).
And then data will be copied from old version to new, for example, by new contract.
Rollback is almost the same: new version is paused,
data is moved back to the old version and old version is activated.
So main task is the addition of methods for obtaining data for old and new versions.  
*	Dispatcher  
![Dispatcher-impl](pics/Dispatcher3.png)  
After voting Government contract changes library address in proxy.
Rollback is changing address back from the new library to the old.
Main goal is create right voting and check storage while setting new address.
