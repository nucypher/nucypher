.. _running-a-node:

======================
Running a Network Node
======================

Nucypher staking operations are divided into two roles - “Staker” and “Worker”.
The Staker can be thought of as a fiduciary administrator that holds NU and collects rewards.
The Worker is bonded to a Staker and performs work on behalf of the Staker.

Due to the complexity of running a node on the network, there are several of ways to
participate depending on your situation:

* Delegate custody of NU and work to a third-party custodian.
* Delegate work via a staking pool or `Node-as-a-Service provider <https://github.com/nucypher/validator-profiles>`_.
* Run your own node:

    .. toctree::
       :maxdepth: 1

       staking_guide
       stake_management
       ursula_configuration_guide
       ../../cli/remote_worker_management_cli

Here is a simple heuristic to help decide on a course of action:

.. image:: ../../.static/img/running_a_node_decision.svg
    :target: ../../.static/img/running_a_node_decision.svg
