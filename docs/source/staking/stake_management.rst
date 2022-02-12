.. _stake-management:

Stake Management
----------------

Several administrative operations can be performed on active stakes:

+----------------------+-------------------------------------------------------------------------------+
| Action               |  Description                                                                  |
+======================+===============================================================================+
|  ``events``          | View blockchain events associated with a staker                               |
+----------------------+-------------------------------------------------------------------------------+


Query Staker Blockchain Events
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

As the Staker and its associated Worker interact with the StakingEscrow smart contract, various on-chain events
are emitted. These events are outlined :doc:`here </contracts_api/main/StakingEscrow>`, and are made accessible via the
``nucypher stake events`` CLI command.


.. note::

    This command is limited to events from the StakingEscrow smart contract and the Staker address associated with
    the Staker's configuration file. For generic and network-wide event queries,
    see :doc:`/references/network_events`.


For simple Staker accounting, events such as ``CommitmentMade``, ``Withdrawn``, and ``Minted`` can
be used. The output of each can be correlated using the period number.

By default, the query is performed from block number 0 i.e. from the genesis of the blockchain. This can be modified
using the ``--from-block`` option.


For a full list of CLI options, run:

.. code::

    $ nucypher stake events --help


For example, to view all of the staking rewards received by the Staker thus far, run:

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --eth-provider <ETH PROVIDER URI> --event-name Minted

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11076964
      ...

``1234567890123456789012`` is in NuNits and equates to approximately 1234.57 NU (1 NU = 10\ :sup:`18` NuNits).


To view staking rewards received by the Staker from block number 11070000 to block number 11916688, run:

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --eth-provider <ETH PROVIDER URI> --event-name Minted --from-block 11070000 --to-block 11916688

    Reading Latest Chaindata...
    Retrieving events from block 11070000 to 11916688

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11076964
      ...


.. important::

    Depending on the Ethereum provider being used, the number of results a query is allowed to return may be limited.
    For example, on Infura this limit is currently 10,000.


To aid with management of this information, instead of outputting the information to the CLI, the event data can
be written to a CSV file using either of the following command-line options:

* ``--csv`` - flag to write event information to a CSV file in the current directory with a default filename
* ``--csv-file <FILEPATH>`` - write event information to a CSV file at the provided filepath

For example,

.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --eth-provider <ETH PROVIDER URI> --event-name Minted --csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    StakingEscrow::Minted events written to StakingEscrow_Minted_2021-02-09_15-23-25.csv


.. code::

    $ nucypher stake events --staking-address <STAKER ADDRESS> --eth-provider <ETH PROVIDER URI> --event-name Minted --csv-file ~/Minted_Events.csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    StakingEscrow::Minted events written to /<HOME DIRECTORY>/Minted_Events.csv
