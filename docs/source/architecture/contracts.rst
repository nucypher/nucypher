.. _contracts:

Ethereum Contracts
==================

Contract Listing
----------------


* ``NuCypherToken`` ERC20 token contract
* ``StakingEscrow`` Legacy staking contract
* ``Adjudicator`` Manages :doc:`the slashing protocol </architecture/slashing>`
* ``Upgradeable`` Base contract for :doc:`upgrading </architecture/upgradeable_proxy_contracts>`
* ``Dispatcher`` Proxy to other contracts and provides upgrading of the ``StakingEscrow`` contract
* ``SimplePREApplication`` Interim application contract for Threshold network
* ``SubscriptionManager`` Holds a policy's fee and distributes them

Deployment Procedure
--------------------

This section provides a step-by-step guide of how NuCypher contracts are deployed.

#. Deploy ``NuCypherToken`` with all future supply tokens
#. Deploy stub for ``StakingEscrow`` with a dispatcher targeting it
#. Deploy Threshold network contracts
#. Deploy ``StakingEscrow`` and retarget its dispatcher by using the ``upgrade(address)`` function
#. Deploy ``SimplePREApplication`` contract
#. Deploy ``SubscriptionManager`` contract

Alice's Contract Interaction
----------------------------

Alice Authors a Blockchain Policy
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Alice uses a network of Ursula staking providers to deploy policies.
In order to take advantage of the network, Alice chooses staking providers and deploys policies with fees for those staking providers.
Alice can choose stakers by herself ("handpicked") or select from the result of ``SimplePREApplication.getActiveStakingProviders(uint256, uint256)`` method - This is  known as ("sampling").
``getActiveStakingProviders`` parameters are:


* Start index in stakers array 
* Maximum number of stakers
  This method will return only active staking providers.

In order to place the fee for a policy, Alice calls the method ``SubscriptionManager.createPolicy(bytes16, address, uint16, uint32, uint32)``\ ,
specifying the policy ID (off-chain generation), the policy owner (could be zero address), the number of nodes, the start and the end timestamp of the policy.
Payment should be added to the transaction in ETH and the amount is ``feeRate * duration * numberOfNodes``\ , where ``duration`` is ``endTimestamp - startTimestamp``.

Staking Provider's Contract Interaction
---------------------------------------

The Staking Provider Bonds to an Operator ("Ursula")
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The staking provider must specify an operator who will make a confirmation and sign on behalf of this staking provider by calling the ``SimplePREApplication.bondOperator(address, address)`` method.
Bonding a new operator is allowed no more than once within ``SimplePREApplication.minOperatorSeconds()``.
Only the operator can make a confirmation.

Ursula Makes a Confirmation
^^^^^^^^^^^^^^^^^^^^^^^^^^^

In order to make a address confirmation, operators call ``SimplePREApplication.confirmOperatorAddress()``.

Contracts Versioning
--------------------

Upgradeable contracts, such as ``StakingEscrow``\, have their version specified in contract doc inside @dev.
Version format is ``|vi.j.k|``\ , where ``i`` - major version, ``j`` - minor version, ``k`` - patch, for example ``|v1.2.3|``\ :


* Different major versions mean different forks and they are not upgradeable
* Minor versions relate to any signatures or state changes inside contract, contracts are upgradeable between minor versions, but have different ABI and follows different agent layers 
* Patches involve changes inside function(s) with signature(s) untouched. All patches with a common minor version can be upgraded from one to another without other changes
