.. _ibex-testnet:

=============
Ibex Testnet
=============

NuCypher provides a public testnet running on the Ethereum Rinkeby testnet meant for stakers and node operators to learn how to
create and manage stakes, set up a node, as well as for internal development purposes.

.. attention::

    Ibex Testnet NU can be obtained by joining the `Discord Server <https://discord.gg/7rmXa3S>`_ and typing
    ``.getfunded <YOUR_STAKER_ETH_ADDRESS>`` in the #testnet-faucet channel. Some ETH is also provided via
    the ``.getfunded`` command, but additional Rinkeby ETH can be obtained from the `Rinkeby faucet <https://faucet.rinkeby.io/>`_.


Stakers and Workers can be configured to use the Ibex testnet using the command line:

.. code::

    # While creating a new staker
    $ nucypher stake init-stakeholder --network ibex --provider <RINKEBY PROVIDER URI>

    # Update an existing staker
    $ nucypher stake config --network ibex --provider <RINKEBY PROVIDER URI>

    # While creating a new worker
    $ nucypher ursula init --network ibex --provider <RINKEBY PROVIDER URI>

    # Update an existing worker
    $ nucypher ursula config --network ibex --provider <RINKEBY PROVIDER URI>


Deployments
-----------

* `NuCypherToken 0x78D591D90a4a768B9D2790deA465D472b6Fe0f18 <https://rinkeby.etherscan.io/address/0x78D591D90a4a768B9D2790deA465D472b6Fe0f18>`_
* `StakingEscrow (Dispatcher) 0x6A6F917a3FF3d33d26BB4743140F205486cD6B4B <https://rinkeby.etherscan.io/address/0x6A6F917a3FF3d33d26BB4743140F205486cD6B4B>`_
* `PolicyManager (Dispatcher) 0x4db603E42E6798Ac534853AA2c0fF5618cb0ebE5 <https://rinkeby.etherscan.io/address/0x4db603E42E6798Ac534853AA2c0fF5618cb0ebE5>`_
* `Adjudicator (Dispatcher) 0xE1d0C09b94ba522BCC1b73922dc1f0b6ca9bEA26 <https://rinkeby.etherscan.io/address/0xE1d0C09b94ba522BCC1b73922dc1f0b6ca9bEA26>`_
