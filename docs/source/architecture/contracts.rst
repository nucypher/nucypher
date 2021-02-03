.. _contracts:

Ethereum Contracts
==================

Contract Listing
----------------


* ``NuCypherToken`` ERC20 token contract
* ``StakingEscrow`` Holds Ursula's stake, stores information about Ursula's activity, and assigns a reward for participating in the NuCypher network. (The ``Issuer`` contract is part of the ``StakingEscrow``\ )
* ``PolicyManager`` Holds a policy's fee and distributes fee by periods
* ``Adjudicator`` Manages :doc:`the slashing protocol </architecture/slashing>`
* ``WorkLock`` Manages token distribution
* ``Upgradeable`` Base contract for :doc:`upgrading </architecture/upgradeable_proxy_contracts>`
* ``Dispatcher`` Proxy to other contracts and provides upgrading of the ``StakingEscrow``, ``PolicyManager`` and ``Adjudicator`` contracts
* ``StakingInterface`` Interface for accessing main contracts from a staking contract
* ``StakingInterfaceRouter`` Router for accessing ``StakingInterface`` contract
* ``AbstractStakingContract`` Base contract for implementing staker-contract concept

Deployment Procedure
--------------------

This section provides a step-by-step guide of how NuCypher contracts are deployed.
For a guide of how to deploy these contracts automatically, see the :doc:`Deployment Guide </guides/deployment_guide>`.

#. Deploy ``NuCypherToken`` with all future supply tokens
#. Deploy stub for ``StakingEscrow`` with a dispatcher targeting it
#. Deploy ``PolicyManager`` with its own dispatcher, also targeting it
#. Deploy ``Adjudicator`` with a dispatcher
#. Deploy ``StakingInterface`` with ``StakingInterfaceRouter`` targeting it
#. Deploy ``WorkLock`` contract
#. Deploy ``StakingEscrow`` and retarget its dispatcher by using the ``upgrade(address)`` function
#. Approve tokens transfer to the ``StakingEscrow`` contract. These tokens are future staking rewards
#. Run the ``initialize(uint256)`` method to initialize the ``StakingEscrow`` contract
#. Approve tokens transfer for distribution to the ``WorkLock`` contract and call ``tokenDeposit(uint256)`` method

Alice's Contract Interaction
----------------------------

Alice Authors a Blockchain Policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Alice uses a network of Ursula stakers to deploy policies.
In order to take advantage of the network, Alice chooses stakers and deploys policies with fees for those stakers.
Alice can choose stakers by herself ("handpicked") or select from the result of ``StakingEscrow.getActiveStakers(uint16, uint256, uint256)`` method - This is  known as ("sampling").
``getActiveStakers`` parameters are:


* Minimum number of periods during which tokens are locked
* Start index in stakers array 
* Maximum number of stakers
  This method will return only active stakers.

In order to place the fee for a policy, Alice calls the method ``PolicyManager.createPolicy(bytes16, address, uint64, address[])``\ ,
specifying the policy ID (off-chain generation), the policy owner (could be zero address), the end timestamp of the policy and the stakers' addresses.
Payment should be added to the transaction in ETH and the amount is ``feeRate * periods * stakers.length``\ , where ``periods`` is ``endTimestampPeriod - currentPeriod + 1``.
The fee rate must be greater than or equal to the minimum fee for each staker in the list.

Alice Revokes a Blockchain Policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When Alice wants to revoke a policy, she calls the ``PolicyManager.revokePolicy(bytes16)`` or ``PolicyManager.revokeArrangement(bytes16, address)``.
Execution of these methods results in Alice recovering all fees for future periods, and also for periods when the stakers were inactive.
Alice can refund ETH for any inactive periods without revoking the policy by using the method ``PolicyManager.refund(bytes16)`` or ``PolicyManager.refund(bytes16, address)``.
If Alice can't execute an on-chain transaction or wants to share the ability to revoke, then she can sign revocation parameters. Anyone who has this signature will be able to revoke policy using ``PolicyManager.revoke(bytes16, address, bytes)``

Staker's Contract Interaction
-----------------------------

Staker Locks Tokens
^^^^^^^^^^^^^^^^^^^

In order to become a participant of the network, a staker stakes tokens in the ``StakingEscrow`` contract.
The staker allows the (staking) contract to perform a transaction using the ``NuCypherToken.approve(address, uint256)`` method
(ERC20 contracts allow access delegation to another address).

After that, the staker transfers some quantity of tokens (\ ``StakingEscrow.deposit(uint256, uint16)``\ ), locking them at the same time.
Alternately the ``NucypherToken.approveAndCall(address, uint256, bytes)`` method can be used.
The parameters are:


* The address of the ``Dispatcher`` that targets the ``StakingEscrow`` contract
* The amount of staked tokens
* The periods for locking (which are serialized into an array of bytes): in python `Web3.toBytes(duration)`, in javascript `web3.utils.hexToBytes(web3.utils.numberToHex(duration))`

When staking tokens, the staker sets the number of periods the tokens will be locked, which must be no less than some minimal locking time (30 periods).
In order to unlock tokens, the staker must be active during the time of locking (and make a commitment each period).
Each stake is represented by the amount of tokens locked, and the stake's duration in periods.
The staker can add a new stake using ``StakingEscrow.deposit(uint256, uint16)`` or ``StakingEscrow.lock(uint256, uint16)`` methods.
The staker can split stake into two parts: one with the same duration and another with an extended duration.
For this purpose, the ``StakingEscrow.divideStake(uint256, uint256, uint16)`` method is used.
The first parameter is used to identify the stake to divide and the last two for the extended part of the stake.
When calculating locked tokens using the ``StakingEscrow.getLockedTokens(address, uint16)`` method, all stakes that are active during the specified period are summed.

The Staker Bonds to a Worker ("Ursula")
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The staker must specify a worker who will make a commitment and sign on behalf of this staker by calling the ``StakingEscrow.bondWorker(address)`` method.
Bonding a new worker is allowed no more than once within ``StakingEscrow.minWorkerPeriods()``.
Only the worker can make a commitment.

Ursula Makes a Commitment
^^^^^^^^^^^^^^^^^^^^^^^^^

In order to make a commitment to the next period, workers call ``StakingEscrow.commitToNextPeriod()`` wherein activities for the next period are registered.
The staker gets a reward for every commitment period.

Ursula Generates Staking Rewards
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

After the period of activity has passed, the staker may call ``StakingEscrow.mint()`` method which computes and transfers tokens to the staker's account.
Also note that calls to ``StakingEscrow.commitToNextPeriod()`` are included the ``StakingEscrow.mint()`` method.

The reward value depends on the fraction of locked tokens for the period (only those who made a commitment are accounted for).
Also, the reward depends on the number of periods during which the tokens will be locked: if the tokens will be locked for half a year, the coefficient is 1.5.
The minimum coefficient is 1 (when tokens will get unlocked in the next period), and the maximum is 2 (when the time is 1 year or more).
The reward is calculated separately for each stake that is active during the mining period and all rewards are summed up.
The order of calling ``StakingEscrow.mint()`` by stakers (e.g. who calls first, second etc) doesn't matter.
Stakers can claim their rewards by using the ``StakingEscrow.withdraw(uint256)`` method. Only non-locked tokens can be withdrawn.

Ursula Generates Policy Fees
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Also the staker gets fees for policies deployed.
Computation of a policy fee happens every time ``StakingEscrow.mint()`` is called by the ``PolicyManager.updateFee(address, uint16)`` method.
In order to take the fee, the staker needs to call method ``withdraw()`` of the contract ``PolicyManager``.
The staker can set a minimum fee rate for a policy. For that, the staker should call the ``PolicyManager.setMinFeeRate(uint256)`` method.

Contracts Versioning
--------------------

Upgradeable contracts, such as ``Adjudicator``\ , ``StakingEscrow``\ , ``PolicyManager`` and ``StakingInterface``\ , have their version specified in contract doc inside @dev.
Version format is ``|vi.j.k|``\ , where ``i`` - major version, ``j`` - minor version, ``k`` - patch, for example ``|v1.2.3|``\ :


* Different major versions mean different forks and they are not upgradeable
* Minor versions relate to any signatures or state changes inside contract, contracts are upgradeable between minor versions, but have different ABI and follows different agent layers 
* Patches involve changes inside function(s) with signature(s) untouched. All patches with a common minor version can be upgraded from one to another without other changes
