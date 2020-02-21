==============
WorkLock Guide
==============

Overview
--------

`WorkLock` is a novel token distribution mechanism we created that requires participants to run NuCypher nodes
to receive NU tokens. Think of it as a replacement for an ICO or an airdrop as a way to distribute initial
tokens, but with a stronger filter for desirable participants (in our case, people who will stake and run nodes on
the network).

There will be an open contribution period in which anyone can contribute ETH to the WorkLock contract. That ETH will
be escrowed on-chain and at the end of the contribution period, stake-locked NU will be distributed pro rata across
contributors. If those contributors use that stake-locked NU to run a node, the NU will eventually unlock and their
escrowed ETH will be returned in full. Alternatively, WorkLock participants can cancel their bid to forgo NU and
recoup their escrowed ETH immediately.

The ``nucypher worklock`` CLI command provides the ability to participate in WorkLock. To better understand the
commands and their options, use the ``--help`` option.

Common CLI flags
----------------

All ``nucypher worklock`` commands share a similar structure:

.. code::

    (nucypher)$ nucypher worklock <ACTION> [OPTIONS] --network <NETWORK> --provider <YOUR PROVIDER URI> --poa

TODO

Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/ubuntu/.ethereum/goerli/geth.ipc`` - Geth Node on Görli testnet running under user ``ubuntu`` (most probably that's what you need).


Show current WorkLock information
---------------------------------

You can obtain information about the current state of WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock status --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


If you want to see detailed information about your current bid, you can specify your bidder address with the ``--bidder-address`` flag:

.. code::

    (nucypher)$ nucypher worklock status --bidder-address <YOUR BIDDER ADDRESS> --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Place a bid
-----------

You can place a bid to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock bid --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Cancel a bid
------------

You can cancel a bid to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock cancel-bid --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Claim your stake
----------------

If your bid was successful, you can claim your tokens as a stake in NuCypher:

.. code::

    (nucypher)$ nucypher worklock claim --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Once claimed, you can check that the stake was created successfully by running:

.. code::

    (nucypher)$ nucypher status stakers --staking-address <YOUR BIDDER ADDRESS> --network {network} --provider <YOUR PROVIDER URI> --poa
