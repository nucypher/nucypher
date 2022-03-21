.. _pre-overview:

Application Overview
====================

All Threshold Network Stakers (legacy KEEP, legacy NU, liquid T) are able to participate
in the PRE application. Threshold Staking can be performed and managed via
the `Threshold dashboard <https://dashboard.threshold.network/overview/network>`_.

.. note::

     The current minimum stake for running a PRE node is (or equivalent to) 40,000 T but is tunable via governance.


For more information about the roles associated with the Threshold Staking contract,
see `here <https://github.com/threshold-network/solidity-contracts/blob/main/docs/rfc-1-staking-contract.adoc>`_.

The PRE Application operations are divided into two roles:

* `Staking Provider`_
* `Operator`_


Staking Provider
----------------

The Staking Provider is a party authorized to operate in the network on behalf of a
given stake owner - it can be the owner itself for self-hosting. The staking provider handles
the everyday operations on the delegated stake without actually owning the staked tokens. A
staking provider cannot transfer delegated staked tokens, but the staking provider’s misbehavior may
result in slashing tokens and thus the entire staked amount is indeed at stake. A Staking Provider
can be specified on the `Threshold Dashboard <https://dashboard.threshold.network/overview/network>`_.


Operator
--------

The Operator (aka "Ursula") is the node, and associated Ethereum address, that provides PRE application service.

It is the :ref:`bonded <bond-operator>` delegate of a Staking Provider and an active network node, performing PRE work on behalf
of a Staking Provider. Nodes must remain online to provide uninterrupted services on-demand.

.. note::

    In the traditional NuCypher Network parlance, ``Worker`` can be used interchangeably
    with the new Threshold Network ``Operator`` term.


Authorizing the PRE Application
-------------------------------
Before the Staking Provider is eligible to participate in the PRE application,
the Authorizer appointed during the stake delegation needs to approve the PRE Application
to use the stake. From the moment of approval, the application is authorized to slash or seize the stake.

Authorization can be performed on the `Threshold Dashboard <https://dashboard.threshold.network/overview/network>`_.


Staking Provider Strategies & Responsibilities
----------------------------------------------

In order to provide the PRE service and receive rewards, there are three options for running a PRE node:

* **Node Delegation**: Delegate running a PRE client to one of the participating *node-as-a-service* :ref:`Staking Providers <node-providers>`. In this
  case, the setup, operation, and monitoring is outsourced, and stakers need only check in occasionally to ensure the provider is handling things as expected.
* **Self-Managed, Manual**: :ref:`Run <running-a-node>` your own PRE node and retain full purview and customization control over the machine(s), installation, dependencies and configuration. In this case, stakers are entirely responsible for setup, operation, and monitoring
  of the PRE client.
* **Self-Managed, Automated**: Run your own PRE node on either Digital Ocean or AWS, leveraging :ref:`automation tools <managing-cloud-nodes>` that speed up and simplify the installation process. In this case too, stakers are entirely responsible for setup, operation, and monitoring of the PRE client.

Note that setting up a PRE node from scratch is non-trivial, but is typically inexpensive and unburdensome to maintain.
PRE end-users expect and require an on-demand service, wherein their *grant*, *revoke* and *re-encryption* requests are answered reliably, correctly, and without interruption.
Hence the most critical responsibility for stakers is ensuring that their PRE node remains online **at all times**. If this is not certain using a local machine, it is highly recommended to use cloud infrastructure instead.


Staker Subsidization (Rewards)
------------------------------
Stakers who have successfully set up their PRE node (confirmed and activated via an on-chain transaction) are eligible to receive rewards, denominated in the native T token.

The sum received will be proportional to one's relative stake size and the duration of time the staker has been active, but independent of the staking rate – i.e. issuance will be computed to target
a `minimum yield <https://forum.threshold.network/t/threshold-network-reward-mechanisms-proposal-i-stable-yield-for-non-institutional-staker-welfare/82>`_.

The target yield and subsequent issuance (total number of tokens distributed monthly to stakers) will be determined by the Threshold Council, and will ramp up over the genesis era of the Threshold Network.

.. important::

    During the genesis era of Threshold Network, to avoid prejudicing against new stakers who have never run a PRE node previously, the first 1-2 months can be considered a *"grace period"* in which
    all stakers will receive the full month's rewards, regardless of which day they commenced staking.
