==============
WorkLock Guide
==============

Overview
--------

`WorkLock` is a novel, permissionless token distribution mechanism, developed at NuCypher, which requires participants to stake ETH and maintain NuCypher nodes in order to receive NU tokens.

WorkLock offers specific advantages over ICO or airdrop as a distribution mechanism, chiefly: it selects for participants who are most likely to strengthen the network because they commit to staking and running nodes.

The WorkLock begins with an open bidding period, during which anyone seeking to participate can send ETH to the WorkLock contract to be escrowed on-chain.
At any time, WorkLock participants can cancel their bid to forgo NU and recoup their escrowed ETH immediately.
Once the bidding period closes, the WorkLock contract doesn't accept more bids, although it still accepts cancellations during an additional time window.
At the end of this cancellation period, stake-locked NU will be distributed according to the following principles:

 - Each bidder receives, at least, the minimum amount of NU needed to stake.
 - All bids will be greater or equal to the minimum allowed bid.
 - In addition to the minimum amount of NU, each bidder receives a portion of the remaining NU, distributed pro rata across all participants, taking into consideration their bid surplus with respect to the minimum bid.
 - If the resulting NU amount is above the maximum allowed NU to stake, then such a bidder has their bid partially refunded until the corresponding amount of NU is within the allowed limits.

Finally, if WorkLock participants use that stake-locked NU to run a node, the NU will eventually unlock and their escrowed ETH will be returned in full.


The ``nucypher worklock`` CLI command provides the ability to participate in WorkLock. To better understand the
commands and their options, use the ``--help`` option.

Common CLI flags
----------------

All ``nucypher worklock`` commands share a similar structure:

.. code::

    (nucypher)$ nucypher worklock <ACTION> [OPTIONS] --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


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


Recall that there's a minimum bid amount needed to participate in WorkLock.


Cancel a bid
------------

You can cancel a bid to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock cancel-bid --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Claim your stake
----------------

Once the claiming window is open, you can claim your tokens as a stake in NuCypher:

.. code::

    (nucypher)$ nucypher worklock claim --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Once claimed, you can check that the stake was created successfully by running:

.. code::

    (nucypher)$ nucypher status stakers --staking-address <YOUR BIDDER ADDRESS> --network {network} --provider <YOUR PROVIDER URI> --poa
    

Check remaining work
--------------------

If you have a stake created from WorkLock, you can check how much work is pending until you can get all your ETH locked in the WorkLock contract back:

.. code::

    (nucypher)$ nucypher worklock remaining-work --network <NETWORK> --provider <YOUR PROVIDER URI> --poa


Refund locked ETH
-----------------

If you've committed some work, you are able to refund proportional part of ETH you've had bid in WorkLock contract:

.. code::

    (nucypher)$ nucypher worklock refund --network <NETWORK> --provider <YOUR PROVIDER URI> --poa
