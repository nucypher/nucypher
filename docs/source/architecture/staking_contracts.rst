.. _staking_contracts:

Staking Contracts
=================

Staking Contracts Architecture
------------------------------


Idea of ``AbstractStakingContract``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Main NuCypher contracts have relations between staker-worker as 1 to 1. Also StakingEscrow forces worker to be real addres. But staker can be a contract. 
Staker can be any contract but still must fulfil the requirements of main contracts. Besides time-to-time NuCypher contracts are updated including ABI. 
This leads that each staking contract have to be upgreadable or have ability to execute any new methods from main contracts what increases complexity of code.
In order to minimize work developers can use ``AbstractStakingContract`` and related contracts.
``AbstractStakingContract`` (and ``InitializableStakingContract``) is including code to access main contracts addresses and upgradeable ABI of these contracts.
``StakingInterfaceRouter`` and ``StakingInterface`` are responsible for keep ABI of main contracts up-to-date and belong to DAO.
So developers no need to worry about accessing main contracts and can concentrate only on logic of staking contract. In the result staking contract even can be not-upgradeable at all.


Versions of ``AbstractStakingContract``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

At the moment we have two differen versions of ``AbstractStakingContract``, very simillar except deploying/initialization phase:
* ``AbstractStakingContract`` itself, simplified version which uses less gas but not suitable for using with ``Proxy`` contract from OpenZeppelin because it has constructor to initialize some constants values.
* ``InitializableStakingContract`` almost same version of contract except initialization logic was extracted from constructor to separate method and it gives ability to use together with ``Proxy``


How to develop
^^^^^^^^^^^^^^

To implement ``AbstractStakingContract`` you need to inherent it in your contract and implements several methods:
* ``isFallbackAllowed()`` defines who allowed to call stakers methods. Simple example when only owner is allowed:

.. code::

	function isFallbackAllowed() public override view returns (bool) {
        return msg.sender == owner();
    }

* ``withdrawTokens(uint256 _value)`` and ``withdrawETH()`` defines who and how can withdraw NU tokens and ETH


How to use
^^^^^^^^^^

In the result implementation will have two ABI:
* Staking contract itself to use developed functions.
* ``StakingInterface`` to access main contracts.


PoolingStakingContractV2
------------------------


Idea
^^^^

Organizes multiple token holders in one large staker with one worker. Delegators pay some percent of reward to worker owner for running node. In the result each delegator can hold even small amount of share in such pool without needing to maintain and run separate worker node.

Roles
^^^^^

Contract has several roles:

* Owner of contract (recommend to give it multisig, DAO or other decentralization government). Owner controls staking functions which means all parameters of staking, when to stake and withdraw reward, restake or not and so on.
* Delegator - token holder who gives the right to use tokens as stake. Delegator can deposit tokens to pool when deposit is enabled and withdraw reward (in tokens and ETH) whenever pool has reward tokens. If pool has enough tokens then delegator can withdraw reward and initial deposit but after this delegator can no longer qualify for the award.
* Worker owner. This address will get all reward for running worker node. Worker owner specified when contract created and to simplify logic can not be changed again. Besides, worker address itself controled by owner of pool.
* Potential role of admistrator (recommend to give it multisig, DAO or other decentralization government). Administrator controls contract upgrading which means can change all logic and contract behaviour. Warning: be aware of who controls this role because even if contract has audited administrator still can change code.

Fees
^^^^

Worker owner get fees in tokens for running worker node. Fee calculated automatically from staking reward - percent of obtained reward. This perent is set during contract deployment. If pool does not generate any reward then worker owner will not get any fees.

Life cycle
^^^^^^^^^^

Before staking owner of pool gathering tokens by enabling deposit. When owner is ready to stake - their close deposit. It's important because there is no difference in rewards between delegator who deposit at first day and who deposit at last. Disabling depositing before staking puts all delegators on a level playing field. After pool start generating reward is highly recommend to not enable deposit again.
Owner also has to specify parameters of staking: size, duration, restaking and winding down. Important to notice that there is no differenece for delegators what reward from which sub-stake is come because they can withdraw reward tokens without any restriction (except their share). In the result if owner withdraws tokens after unlocking specific sub-stake - all tokens will available for all delegators.
