.. _staking_contracts:

Staking Contracts
=================

Architecture
------------

NuCypher :doc:`Main Contracts</contracts_api/index>` enforce a 1:1 relationship between Staker and Worker roles. Even
though the ``StakingEscrow`` smart contract forces the Worker address to be an Ethereum account, the Staker address
can be that of a smart contract. Any staking contract must fulfil the requirements of the Main contracts, which
can be subsequently updated, including ABIs. Therefore, staking contracts must either be upgradeable or
have the ability to route to new methods in the Main contracts.


Development
-----------

To minimize development efforts, developers can use the ``AbstractStakingContract`` smart contract API.
``AbstractStakingContract`` accesses Main Contracts' addresses through
:doc:`StakingInterface </contracts_api/staking/StakingInterface>` and
:doc:`StakingInterfaceRouter </contracts_api/staking/StakingInterfaceRouter>`, so that developers do not need to access
the Main contracts directly or be concerned about upgraded or incompatible ABIs, and can concentrate on the core
logic of their staking contract.

This feature makes it possible for the developer's staking smart contract to not need to be upgradeable. The
benefit of the contract not being upgradeable is that it reassures users that once the contract is deployed, it cannot
be modified.


Implementation
^^^^^^^^^^^^^^

Currently, there are two versions of ``AbstractStakingContract`` which are very similar except for how they
are initialized:

* ``AbstractStakingContract`` - the constructor is used to initialize values. It is a simplified version that uses
  less gas but is not suitable to use with OpenZeppelin's ``Proxy`` contract because of the initialization logic in the
  constructor
* ``InitializableStakingContract`` - the initialization logic was extracted from the constructor and
  instead provided via an initialization method which allows it to be used with
  OpenZeppelin's ``Proxy`` contract

These contracts can be inherited, and the following methods implemented:

* ``isFallbackAllowed()`` - defines who is allowed to call Staker methods. A simple example to allow only the owner:

    .. code::

        function isFallbackAllowed() public override view returns (bool) {
            return msg.sender == owner();
        }

* ``withdrawTokens(uint256 _value)`` - the process of withdrawal of NU from the contract
* ``withdrawETH()`` - the process of withdrawal of ETH from the contract


This implementation will result in two ABIs:

* The developer's staking contract implementation
* ``StakingInterface`` to access main contracts


Staking Pool Contract
---------------------

In an effort to reduce the friction associated with staking NU and running a Worker,
a :doc:`simple staking pool smart contract </contracts_api/staking/PoolingStakingContractV2>` is provided.

.. note::

    .. TODO: add link to audit report

    While NuCypher has had the staking pool contract audited, there remains smart contract risk and there are
    no guarantees about the logic. There is also the risk of trust in the *Owner* of the contract to not
    be malicious. See the `Risks`_ section below.


The staking pool smart contract organizes multiple NU holders into one large Staker which delegates to a
single Worker. Each token holder can deposit any amount of NU into the pool and will be entitled to the pro-rata
share of the pool and rewards without needing to maintain and run their own Worker. Token holders will pay a
percentage of NU staking rewards received to the owner of the Worker for running a node.

There is the added benefit of reducing overall Worker gas costs by combining multiple Stakers, each of whom would
have needed to a Worker otherwise, into one large Staker that uses a single Worker that performs work on
behalf of the staking pool.


Contract Roles
^^^^^^^^^^^^^^

The pooling contract has several roles:

* *Owner* - controls the staking functions including all parameters of staking e.g. ``restake``, ``winddown``, etc.

    .. important::

      It is recommended to use a multisig, DAO or other decentralized governance mechanism.

* *Worker Owner* - the owner of the Worker that runs on behalf of the staking pool; only this address can
  withdraw the worker's collected fee
* *Delegators* - the NU holders who deposit NU into the pooling contract
* *Administrator (Optional)* - oversees contract upgrades which allow modification to all contract logic
  and behaviour; this role only applies when the contract is upgradeable and the OpenZeppelin's ``Proxy`` contract
  is utilized

    .. warning::

      Be cautious of who is bestowed the Administrator role because even if the pooling contract was audited,
      the Administrator can modify/upgrade the contract code after deployment. **It is recommended to use a
      multisig, DAO or other decentralized governance mechanism.**


Worker Fees
^^^^^^^^^^^
The *Worker Owner* receives a percentage of NU staking rewards as a fee for running a Worker on behalf of the
staking pool. This percentage is configured during contract deployment. The implication here is that if the pool
does not generate any rewards then the *Worker Owner* will not receive any fee.


Contract Lifecycle
^^^^^^^^^^^^^^^^^^

* The *Owner* deploys the contract and initializes it by specifying the Worker fee percentage and the *Worker Owner*
  address.
* Once deployed, deposits are enabled by default to start accepting deposits from *Delegators*.
* At any point before the *Owner* creates a stake, a Delegator can exit the pool and recoup their original deposit via
  the ``withdrawAll`` function.
* After the intended deposits have been received, the *Owner* specifies staking parameters to create a stake: size,
  duration, restaking, winddown etc., and bonds the stake to the Worker address.
* Once the *Owner* creates a stake, the ability to deposit into the pool is automatically disabled to prevent any
  new deposits. Disabling deposits ensures that there is clear proportional ownership of the pool and its received
  rewards. This is a much simpler model for determining proportional ownership than allowing deposits after
  staking has started and after staking rewards and policy fees have been received.
* Once staking rewards and policy fees have been generated, the *Owner* can withdraw the staking rewards from
  ``StakingEscrow`` to the pool, and *Delegators* can obtain their proportional share of the proceeds via
  the ``withdrawTokens`` and ``withdrawETH`` functions. Note that this is only for staking rewards and policy fees,
  **not** their original deposit. The original deposit can only be withdrawn once the stake has expired.
* Throughout this process, the *Worker Owner* can retrieve their Worker commission via the
  ``withdrawWorkerReward`` function.
* When the stake eventually becomes expired and the *Owner* withdraws the pool's escrowed NU from ``StakingEscrow``,
  then all of the withdrawn NU will be available for *Delegators* to withdraw including their deposit, and
  proportional to their share.
* *Delegators* that want to withdraw both their original deposit and all of their proportional rewards i.e. exit
  the pool, they can do so via the ``withdrawAll`` function.


Risks
^^^^^

* The *Owner* / *Administrator* making the pooling contract Upgradeable in which case all logic can be modified.
* The *Owner* disabling ``winddown`` when creating the stake, and never turning it on, thereby keeping the locked
  duration constant until ``winddown`` is enabled, potentially never.
* The *Owner* not running a Worker after creating the stake; by not running a node, the stake will be locked until the
  work is performed.
