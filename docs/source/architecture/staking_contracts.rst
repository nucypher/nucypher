.. _staking_contracts:

Staking Contracts
=================

Architecture
------------

NuCypher :doc:`Main Contracts</contracts_api/index>` enforce a 1:1 relation between Staker and Worker roles. Even
though the ``StakingEscrow`` smart contract forces the Worker address to be an Ethereum account, the Staker address
can be that of a smart contract. Any staking smart contract must fulfil the requirements of the Main contracts, which
can subsequently be updated including ABIs. Therefore, any staking contract must either be upgradeable or
have the ability to route to new methods in the Main contracts.


Development
-----------

In order to minimize development efforts, developers can use the ``AbstractStakingContract`` smart contract.
``AbstractStakingContract`` accesses Main Contracts' addresses through
:doc:`StakingInterface </contracts_api/staking/StakingInterface>` and
:doc:`StakingInterfaceRouter </contracts_api/staking/StakingInterfaceRouter>`, so that developers do not need to access
Main contracts directly or be concerned about upgraded ABIs, and can concentrate on the core logic of their
staking contract.

This feature makes it possible for the developer's staking smart contract to not need to be upgradeable. The
benefit of the contract not being upgradeable is that it reassures users that once the contract is deployed, it cannot
be modified.


Implementation
^^^^^^^^^^^^^^

Currently, there are two versions of ``AbstractStakingContract`` which are very similar except for how they
are initialized:

* ``AbstractStakingContract`` - constructor is used to initialize values. It is a simplified version that uses
  less gas, but is not suitable to use with OpenZeppelin's ``Proxy`` contract because of the constructor
* ``InitializableStakingContract`` - the initialization logic was extracted from the constructor and
  can be set via an initialization method which gives it the ability to be used with OpenZeppelin's ``Proxy`` contract

These contracts can be inherited, and the following methods should be implemented:

* ``isFallbackAllowed()`` - defines who is allowed to call Staker methods. A simple example for only allowing the owner:

    .. code::

        function isFallbackAllowed() public override view returns (bool) {
            return msg.sender == owner();
        }

* ``withdrawTokens(uint256 _value)`` - the process of withdrawal of NU from the contract
* ``withdrawETH()`` - the process of withdrawal of ETH from the contract


This implementation will result in two ABIs:

* The staking contract implementation
* ``StakingInterface`` to access main contracts


Staking Pool Contract
---------------------

In an effort to reduce the friction associated with staking NU and running a Worker node,
a :doc:`simple staking pool smart contract </contracts_api/staking/PoolingStakingContractV2>` is provided.

The staking pool contract organizes multiple NU holders into one large Staker which delegates to a
single Worker. Each token holder can deposit any amount of NU into the pool and will be entitled to the pro-rata
share of the pool and rewards without needing to maintain and run their Worker node. Token holders will pay a
percentage of NU staking rewards to the owner of the Worker for running a node.

There is the added benefit of reducing Worker gas costs by combining multiple Stakers, each with their Worker, into
one large Staker that uses a single Worker.


Contract Roles
^^^^^^^^^^^^^^

The Pooling Contract has several roles:

* *Owner* - controls the staking functions which means all parameters of staking, when to stake and withdraw
  reward, staking properties e.g. restake, winddown, etc.

    .. important::

      It is recommended to use a multisig, DAO or other decentralization governance mechanism.

* *Worker Owner* - the owner of the Worker that runs on behalf of the staking pool; only this address can
  withdraw the worker's collected fee
* *Delegators* - the NU holders who deposit NU into the pooling contract.
* *Administrator (Optional)* - oversees contract upgrades which allow modification to all contract logic
  and behaviour. This role only applies when the contract is upgradeable and the OpenZeppelin's ``Proxy`` contract
  is utilized.

    .. warning::

      Be cautious of who is bestowed the Administrator role because even if the pooling contract was audited,
      the Administrator can modify/upgrade the contract code after deployment. **It is recommended to use a
      multisig, DAO or other decentralization governance mechanism.**


Worker Fees
^^^^^^^^^^^
The *Worker Owner* receives a percentage of NU staking rewards as a fee for running a Worker node on behalf of the
staking pool. This percentage can be configured during contract deployment. The implication here is that if the pool
does not generate any rewards then the *Worker Owner* will not receive their fee.


Contract Lifecycle
^^^^^^^^^^^^^^^^^^

* *Owner* deploys contract and initializes it by specifying the Worker fee percentage and the *Worker Owner* address
* Once deployed, deposits are enabled by default to start accepting deposits from *Delegators*
* After the intended deposits have been received, the *Owner* should disable deposits preventing any more deposits.
  Disabling deposits before staking ensures that there is clear proportional ownership of the pool and its rewards.
  Once the pool starts generating rewards it is highly recommended to keep deposits disabled. This is a much simpler
  model for determining proportional ownership than allowing deposits after staking started and prior staking rewards
  and policy fees have already been received.
* *Owner* specifies staking parameters to create a stake: size, duration, restaking, winddown etc., and bonds the stake
  to the Worker address
* Once staking rewards and policy fees have been generated, the *Owner* can collect the rewards from ``StakingEscrow``
  and then *Delegators* can obtain their proportional share of the proceeds via the ``withdrawTokens`` and ``withdrawETH``
  functions. Note that this is only for staking rewards and policy fees, not their original deposit.
* Throughout this process the *Worker Owner* can retrieve their Worker commission via the ``withdrawWorkerReward`` function.
* If the eventually stake becomes unlocked and the *Owner* withdraws NU from ``StakingEscrow``, then all of the
  withdrawn NU will be available for *Delegators* to withdraw, proportional to their share.
* *Delegators* that want to withdraw both their original deposit and rewards i.e. exit the pool, they can do so
  via the ``withdrawAll`` function.
