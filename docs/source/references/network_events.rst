Network Events
==============

When there is an interaction with NuCypher smart contracts, various on-chain events are emitted. These events are
defined in the :doc:`Contracts API </contracts_api/index>`, and they are queryable via the ``nucypher status events``
CLI command, and allows for any NuCypher Network event to be queried.


Querying Events
---------------

Since the number of events returned may be large, by default the query is limited to events within block numbers for the
current period. However, this is configurable using the ``--from-block`` option.

.. important::

    Depending on the Ethereum provider being used, the number of results a query is allowed to return may be limited.
    For example, on Infura this limit is currently 10,000.


For a full list of CLI options, run:

.. code::

    $ nucypher status events --help


For example, to view the staking rewards received by all Stakers in the current period, run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-name Minted

    Reading Latest Chaindata...
    Retrieving events from block 11916688 to latest

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER_ADDRESS 1>, period: 18681, value: 1234567890123456789012, block_number: 11916689
      - (EventRecord) staker: <STAKER ADDRESS 2>, period: 18681, value: 1234567890123456789012, block_number: 11916692
      - (EventRecord) staker: <STAKER ADDRESS 3>, period: 18681, value: 1234567890123456789012, block_number: 11916692
      - (EventRecord) staker: <STAKER ADDRESS 4>, period: 18681, value: 1234567890123456789012, block_number: 11916692
      ...

The value ``1234567890123456789012`` is in NuNits and equates to approximately 1234.57 NU (1 NU = 10\ :sup:`18` NuNits).


To view the staking rewards received by all Stakers from block number ``11916685`` to ``11916688``, run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-name Minted --from-block 11916685 --to-block 11916688

    Reading Latest Chaindata...
    Retrieving events from block 11916685 to 11916688

    --------- StakingEscrow Events ---------

    Minted:
      - (EventRecord) staker: <STAKER_ADDRESS 1>, period: 18681, value: 1234567890123456789012, block_number: 11916687
      - (EventRecord) staker: <STAKER_ADDRESS 2>, period: 18681, value: 1234567890123456789012, block_number: 11916687
      - (EventRecord) staker: <STAKER_ADDRESS 3>, period: 18681, value: 1234567890123456789012, block_number: 11916687
      - (EventRecord) staker: <STAKER ADDRESS 4>, period: 18681, value: 1234567890123456789012, block_number: 11916687
      ...


To view every PolicyManager smart contract event thus far, run:

.. code::

    $  nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name PolicyManager --from-block 0

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- PolicyManager Events ---------

    ArrangementRevoked:
    FeeRateRangeSet:
      - (EventRecord) sender: 0xb6bfF48574B722F3BFf0C29c9e1b631dD19c1A93, min: 50000000000, defaultValue: 50000000000, max: 500000000000, block_number: 11057893
    MinFeeRateSet:
      - (EventRecord) node: 0xd4CA3a2F1046B845Aad5fe16211fd1686421e175, value: 500000000000, block_number: 11466651
    OwnershipTransferred:
      - (EventRecord) previousOwner: 0x0000000000000000000000000000000000000000, newOwner: 0xebA17F35955E057a8d2e74bD4638528851d8E063, block_number: 10763539
      - (EventRecord) previousOwner: 0xebA17F35955E057a8d2e74bD4638528851d8E063, newOwner: 0xb6bfF48574B722F3BFf0C29c9e1b631dD19c1A93, block_number: 11057541
    ...


Event Filters
-------------

To aid with query limits and more specific queries, events can be filtered using the ``--event-filter``
option. Multiple ``--event-filter`` options can be defined, but note that only properties classified
as ``indexed`` in the event's solidity definition can be used as a filter.

For example, to view all of the commitments ever made by the Worker associated with a specific Staker run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-name CommitmentMade --event-filter staker=<STAKING_ADDRESS> --from-block 0

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    CommitmentMade:
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11057641
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11063640
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18553, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18554, value: 1234567890123456789012, block_number: 11076964
      ...

To view the commitment made by the Worker associated with a specific Staker in period 18552, run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-name CommitmentMade --event-filter staker=<STAKING_ADDRESS> --event-filter period=18552 --from-block 0

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    CommitmentMade:
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11063640


CSV Output
----------

CLI output can be cumbersome when trying to generate insights and correlate different events. Instead, the event
data can be written to a CSV file using either of the following command-line options:

* ``--csv`` - flag to write event information to default CSV files in the current directory with default filenames
* ``--csv-file <FILEPATH>`` - write event information to a specific CSV file at the provided filepath


For example,

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name PolicyManager --event-name PolicyCreated --from-block 0 --csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- PolicyManager Events ---------

    PolicyManager::PolicyCreated events written to PolicyManager_PolicyCreated_2021-02-24_20-02-32.csv


.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name PolicyManager --event-name PolicyCreated --from-block 0 --csv-file ~/Policy_Events.csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- PolicyManager Events ---------

    PolicyManager::PolicyCreated events written to /<HOME DIRECTORY>/Policy_Events.csv


To write every PolicyManager smart contract event thus far to corresponding CSV files, run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name PolicyManager --from-block 0 --csv

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- PolicyManager Events ---------

    No PolicyManager::ArrangementRevoked events found
    PolicyManager::FeeRateRangeSet events written to PolicyManager_FeeRateRangeSet_2021-02-24_20-47-00.csv
    PolicyManager::MinFeeRateSet events written to PolicyManager_MinFeeRateSet_2021-02-24_20-47-01.csv
    PolicyManager::OwnershipTransferred events written to PolicyManager_OwnershipTransferred_2021-02-24_20-47-01.csv
    PolicyManager::PolicyCreated events written to PolicyManager_PolicyCreated_2021-02-24_20-47-01.csv
    No PolicyManager::PolicyRevoked events found
    No PolicyManager::RefundForArrangement events found
    No PolicyManager::RefundForPolicy events found
    PolicyManager::StateVerified events written to PolicyManager_StateVerified_2021-02-24_20-47-06.csv
    PolicyManager::UpgradeFinished events written to PolicyManager_UpgradeFinished_2021-02-24_20-47-06.csv
    PolicyManager::Withdrawn events written to PolicyManager_Withdrawn_2021-02-24_20-47-06.csv


To write StakingEscrow events for a specific Staker for the current period to corresponding CSV files, run:

.. code::

    $ nucypher status events --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-filter staker=<STAKING_ADDRESS> --csv

    Reading Latest Chaindata...
    Retrieving events from block 11929449 to latest

    --------- StakingEscrow Events ---------

    StakingEscrow::CommitmentMade events written to StakingEscrow_CommitmentMade_2021-02-26_00-11-53.csv
    No StakingEscrow::Deposited events found
    No StakingEscrow::Divided events found
    No StakingEscrow::Donated events found
    No StakingEscrow::Initialized events found
    No StakingEscrow::Locked events found
    StakingEscrow::Merged events written to StakingEscrow_Merged_2021-02-26_00-12-27.csv
    StakingEscrow::Minted events written to StakingEscrow_Minted_2021-02-26_00-12-29.csv
    No StakingEscrow::OwnershipTransferred events found
    No StakingEscrow::Prolonged events found
    No StakingEscrow::ReStakeLocked events found
    No StakingEscrow::ReStakeSet events found
    No StakingEscrow::Slashed events found
    No StakingEscrow::SnapshotSet events found
    No StakingEscrow::StateVerified events found
    No StakingEscrow::UpgradeFinished events found
    No StakingEscrow::WindDownSet events found
    No StakingEscrow::Withdrawn events found
    No StakingEscrow::WorkMeasurementSet events found
    No StakingEscrow::WorkerBonded events found


.. note::

    If there were no events found, a CSV file is not written to.


.. important::

    When using the ``--csv-file`` option, since different events can have different
    properties, the ``--event-name`` and ``--contract-name`` options must be specified. If querying for multiple
    events at the same time i.e. running the command without ``--event-name``, the ``--csv`` option can be used
    to generate separate default filenames for the different events.
