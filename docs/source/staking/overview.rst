.. _running-a-node:

Threshold Staking
=================

All Threshold Network stakers (legacy KEEP, legacy NU, liquid T) are able to participate
in the PRE application. Threshold Staking can be performed and managed via
the `Threshold dashboard <https://dashboard.threshold.network/overview/network>`_.

For more information about the roles associated with the Threshold Staking contract,
see `here <https://github.com/threshold-network/solidity-contracts/blob/main/docs/rfc-1-staking-contract.adoc>`_.


PRE Application Overview
========================

The PRE Application operations are divided into two roles - “Staking Provider” and “Operator”.


Staking Provider
----------------
The Staking Provider is a party authorized to operate in the network on behalf of a
given stake owner - it can be the owner itself for self-hosting. The staking provider handles
the everyday operations on the delegated stake without actually owning the staked tokens. A
staking provider cannot transfer delegated staked tokens, but the staking provider’s misbehavior may
result in slashing tokens and thus the entire staked amount is indeed at stake. A Staking Provider
can be specified on the `Threshold dashboard <https://dashboard.threshold.network/overview/network>`_.


Operator
--------

The Operator (aka "Ursula") is the node that provides PRE application service.

It is the bonded delegate of a Staking Provider and an active network node, performing PRE work on behalf
of a Staking Provider. Ursulas must remain online to provide uninterrupted services on-demand.

.. note::

    In the traditional NuCypher Network parlance, ``Worker`` can be used interchangeably
    with the new Threshold Network ``Operator`` term.


Authorizing the PRE Application
-------------------------------
Before the Staking Provider is eligible to participate in the PRE application,
the Authorizer appointed during the stake delegation needs to approve the PRE Application
to use the stake. From the moment of approval, the application is authorized to slash or seize the stake.

Authorization can be performed on the `Threshold dashboard <https://dashboard.threshold.network/overview/network>`_.


Staker Strategies & Responsibilities
------------------------------------

In order to provide the PRE service and receive rewards, there have three options for running a PRE node:

* **Node Delegation**: Delegate running a PRE client to one of the participating :ref:`Node-as-a-Service providers <node-providers>`. In this
  case, the setup, operation, and monitoring is outsourced, and stakers need only check in occasionally to ensure the provider is handling things as expected.
* **Self-Managed, Manual**: :ref:`Run<running-a-node>` your own PRE node and retain full purview and customization control over the machine(s), installation, dependencies and configuration. In this case, stakers are entirely responsible for setup, operation, and monitoring
  of the PRE client.
* **Self-Managed, Automated**: Run your own PRE node on either Digital Ocean or AWS, leveraging :ref:`automation tools <managing-cloud-workers>` that speed up and simplify the installation process. In this case too, stakers are entirely responsible for setup, operation, and monitoring of the PRE client.

Note that setting up a PRE node from scratch is non-trivial, but is typically inexpensive and unburdensome to maintain.
PRE end-users expect and require an on-demand service, wherein their *grant*, *revoke* and *re-encryption* requests are answered reliably, correctly, and without interruption.
Hence the most critical responsibility for stakers is ensuring that their PRE node remains online **at all times**. If this is not certain using a local machine, it is highly recommended to use cloud infrastructure instead.
