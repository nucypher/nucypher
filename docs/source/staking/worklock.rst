.. _worklock-guide:

========
WorkLock
========

Overview
--------

:ref:`worklock-architecture` is the distribution mechanism for the NuCypher token.

.. important::

    The Ethereum address for the WorkLock contract is
    `0xe9778E69a961e64d3cdBB34CF6778281d34667c2 <https://etherscan.io/address/0xe9778e69a961e64d3cdbb34cf6778281d34667c2>`_.
    Please make sure that you interact with this contract address and no other.


WorkLock CLI
------------

The ``nucypher worklock`` CLI command provides the ability to participate in WorkLock. To better understand the
commands and their options, use the ``--help`` option.

All ``nucypher worklock`` commands share a similar structure:

.. code::

    (nucypher)$ nucypher worklock <COMMAND> [OPTIONS] --provider <YOUR PROVIDER URI>


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``ipc:///home/<username>/.ethereum/geth.ipc`` - IPC Socket-based JSON-RPC server
    - ``https://<host>`` - HTTP(S)-based JSON-RPC server
    - ``wss://<host>:8080`` - Websocket(Secure)-based JSON-RPC server

If you're using a network different than NuCypher ``mainnet`` (like for example our ``ibex`` testnet),
you can include the ``--network <NETWORK>`` option to any WorkLock command.

Show current WorkLock information
---------------------------------

You can obtain information about the current state of WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock status --provider <YOUR PROVIDER URI>


The following is an example output of the ``status`` command (hypothetical values):

.. code::

    Reading Latest Chaindata...

    WorkLock (0xe9778E69a961e64d3cdBB34CF6778281d34667c2)

    Time
    ══════════════════════════════════════════════════════

    Escrow Period (Open)
    ------------------------------------------------------
    Allocations Available . No
    Start Date ............ 2020-09-01 00:00:00+00:00
    End Date .............. 2020-09-28 23:59:59+00:00
    Duration .............. 27 days, 23:59:59
    Time Remaining ........ 26 days, 15:43:43

    Cancellation Period (Open)
    ------------------------------------------------------
    End Date .............. 2020-09-30 23:59:59+00:00
    Duration .............. 29 days, 23:59:59
    Time Remaining ........ 28 days, 15:43:43


    Economics
    ══════════════════════════════════════════════════════

    Participation
    ------------------------------------------------------
    Lot Size .............. 225000000 NU
    Min. Allowed Escrow ... 5 ETH
    Participants .......... 71
    ETH Supply ............ 620.65 ETH
    ETH Pool .............. 620.65 ETH

    Base (minimum escrow)
    ------------------------------------------------------
    Base Deposit Rate ..... 3000 NU per base ETH

    Bonus (surplus over minimum escrow)
    ------------------------------------------------------
    Bonus ETH Supply ...... 265.65 ETH
    Bonus Lot Size ........ 223935000 NU
    Bonus Deposit Rate .... 842970 NU per bonus ETH
    
    Refunds
    ------------------------------------------------------
    Refund Rate Multiple .. 8.00
    Bonus Refund Rate ..... 105371.25 units of work to unlock 1 bonus ETH
    Base Refund Rate ...... 375.0 units of work to unlock 1 base ETH

        * NOTE: bonus ETH is refunded before base ETH


For the less obvious values in the output, here are some definitions:

    - Lot Size
        NU to be allocated by WorkLock
    - ETH Supply
        Sum of all ETH escrows that have been placed
    - ETH Pool
        Current ETH balance of WorkLock that accounts for refunded ETH for work performed i.e. `ETH Supply` - `Refunds for Work`
    - Refund Rate Multiple
        Indicates how quickly your ETH is unlocked relative to the deposit rate e.g. a value of ``4`` means that you get your ETH refunded 4x faster than the rate used when you were allocated NU
    - Base Deposit Rate
        Amount of NU to be allocated per base ETH in WorkLock
    - Bonus ETH Supply
        Sum of all bonus ETH escrows that have been placed i.e. sum of all ETH above minimum escrow
    - Bonus Lot Size
        Amount of NU that is available to be allocated based on the bonus part of escrows
    - Bonus Deposit Rate
        Amount of NU to be allocated per bonus ETH in WorkLock
    - Bonus Refund Rate
        Units of work to unlock 1 bonus ETH
    - Base Refund Rate
        Units of work to unlock 1 base ETH


If you want to see specific information about your current escrow, you can specify your participant address with the ``--participant-address`` flag:

.. code::

    (nucypher)$ nucypher worklock status --participant-address <YOUR PARTICIPANT ADDRESS> --provider <YOUR PROVIDER URI>

The following output is an example of what is included when ``--participant-address`` is used

.. code::

    WorkLock Participant <PARTICIPANT ADDRESS>
    =====================================================
    NU Claimed? .......... No
    Total Escrow ......... 22 ETH
        Base ETH ......... 15 ETH
        Bonus ETH ........ 7 ETH
    NU Allocated ......... 68000 NU

    Completed Work ....... 0
    Available Refund ..... 0 ETH

    Refunded Work ........ 0
    Remaining Work ....... <REMAINING WORK>

Alternatively, when the NU has been allocated, the following is an example of the output

.. code::

    WorkLock Participant <PARTICIPANT ADDRESS>
    =====================================================
    NU Claimed? .......... Yes
    Locked ETH ........... 22 ETH

    Completed Work ....... 0
    Available Refund ..... 0 ETH

    Refunded Work ........ 0
    Remaining Work ....... <REMAINING WORK>

where,

    - Total Escrow
        WorkLock Escrow
    - Base ETH
        Minimum required escrow
    - Bonus ETH
        Surplus over minimum escrow
    - NU Allocated
        Allocation of NU
    - Locked ETH
        Remaining ETH to be unlocked via completion of work
    - NU Claimed
        Whether the allocation of NU tokens has been allocated or not
    - Completed Work
        Work already completed by the participant
    - Available Refund
        ETH portion available to be refunded due to completed work
    - Refunded Work
        Work that has been completed and already refunded
    - Remaining Work
        Pending amount of work required before all of the participant's escrowed ETH will be refunded


.. note::

    ``--signer`` is not required if you are running a local ethereum node or your ``--provider`` is the
    same entity as your signer.


Place an escrow (or increase existing one)
------------------------------------------

You can place an escrow to WorkLock (or if you already have one, increase the amount) by running:

.. code::

    (nucypher)$ nucypher worklock escrow --provider <YOUR PROVIDER URI> --signer <SIGNER_URI>


Recall that there's a minimum escrow amount of 5 ETH needed to participate in WorkLock.


Cancel an escrow
----------------

You can cancel an escrow to WorkLock by running:

.. code::

    (nucypher)$ nucypher worklock cancel-escrow --provider <YOUR PROVIDER URI> --signer <SIGNER_URI>


Claim your stake
----------------

Once the allocation window is open, you can claim your NU as a stake in NuCypher:

.. code::

    (nucypher)$ nucypher worklock claim --provider <YOUR PROVIDER URI> --signer <SIGNER_URI>


Once allocated, you can check that the stake was created successfully by running:

.. code::

    (nucypher)$ nucypher status stakers --staking-address <YOUR PARTICIPANT ADDRESS> --provider <YOUR PROVIDER URI>
    

Check remaining work
--------------------

If you have a stake created from WorkLock, you can check how much work is pending until you can get all your ETH locked in the WorkLock contract back:

.. code::

    (nucypher)$ nucypher worklock remaining-work --provider <YOUR PROVIDER URI>


Refund locked ETH
-----------------

If you've committed some work, you are able to refund proportional part of ETH you've escrowed in the WorkLock contract:

.. code::

    (nucypher)$ nucypher worklock refund --provider <YOUR PROVIDER URI> --signer <SIGNER_URI>
