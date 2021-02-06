.. _running-a-node:

Stakers and Workers
===================

NuCypher staking operations are divided into two roles - “Staker” and “Worker”.
The Staker can be thought of as a fiduciary administrator that holds NU and collects rewards.
The Worker is bonded to a Staker and performs work on behalf of the Staker.

Staker Overview
----------------

A nucypher staker is a holder of NU and manager of one or more stakes. NU is an ERC-20 token that underpins the network. Stakes are initiated by locking NU into
the *"Staking Escrow "* contract for a fixed duration of time. Staked NU earns two income streams: inflation
rewards (NU) and policy fees (ETH). Staked NU gradually unlocks with each completed period (24 hours),
depending on *re-stake* and *wind-down* configuration options.

Active network participation (work) is delegated to a *Worker* node through *bonding*.
There is a 1:1 relationship between the roles; One Staker to one Worker. A Staker controls a single Ethereum
account and may have multiple substakes, but only ever has one Worker bonded at a time. To ensure the integrity of the network and its service quality,
staked NU can be :ref:`slashed <slashing-protocol>` due to misbehaviour, deliberate or unintentional, by the
corresponding worker.

Worker Overview
----------------

*Worker* - (aka "Ursula") Active network participant who carries out threshold cryptography operations.

The Worker is the bonded delegate of a Staker and an active network node, performing work on behalf of a Staker.
Workers must remain online to provide uninterrupted services on-demand, signalling their availability with
commitment transactions every period (24 hours).


Staker and Worker Delegation
-----------------------------

There are several strategies for running and maintaining a stake:

* Delegate custody of NU and work to a third-party custodian (Staker Delegation).
* Delegate work via a staking pool or `Node-as-a-Service provider <https://github.com/nucypher/validator-profiles>`_ (Worker Delegation).
* Control the Staker yourself and run your own worker (Self Directed).

Here is a simple heuristic to help decide on a course of action:

.. image:: ../.static/img/running_a_node_decision.svg
    :target: ../.static/img/running_a_node_decision.svg
