=======================
NuCypher WorkLock Guide
=======================

Overview
--------

TODO

To better understand the commands and their options, use the ``--help`` option.

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

You can obtain information of current state of WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock status --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


If you want to see detailed information of your current bid, you can also introduce your bidder address with the ``--bidder-address`` flag:

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