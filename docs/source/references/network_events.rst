PRE Application Events
======================

When there is an interaction with PRE Application smart contracts, various on-chain events are emitted. These events are
queryable via the ``nucypher status events``
CLI command, and allows for any PRE Application event to be queried.


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


Event Filters
-------------

To aid with query limits and more specific queries, events can be filtered using the ``--event-filter``
option. Multiple ``--event-filter`` options can be defined, but note that only properties classified
as ``indexed`` in the event's solidity definition can be used as a filter.

The event filter can be defined as follows, ``--event-filter <PARAMETER_NAME>=<FILTER_VALUE>``.


Legacy Events
-------------

To query for events related to the NuCypher Network prior to the merge to Threshold Network,
e.g. ``CommitmentMade`` or ``Minted``, use the ``--legacy`` flag.

For example, to view all of the legacy NuCypher Network commitments ever made by the node associated with a specific Staker run:

.. code::

    $ nucypher status events --legacy --eth-provider <ETH PROVIDER URI> --contract-name StakingEscrow --event-name CommitmentMade --event-filter staker=<STAKING_ADDRESS> --from-block 0

    Reading Latest Chaindata...
    Retrieving events from block 0 to latest

    --------- StakingEscrow Events ---------

    CommitmentMade:
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18551, value: 1234567890123456789012, block_number: 11057641
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18552, value: 1234567890123456789012, block_number: 11063640
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18553, value: 1234567890123456789012, block_number: 11070103
      - (EventRecord) staker: <STAKER_ADDRESS>, period: 18554, value: 1234567890123456789012, block_number: 11076964
      ...


CSV Output
----------

CLI output can be cumbersome when trying to generate insights and correlate different events. Instead, the event
data can be written to a CSV file using either of the following command-line options:

* ``--csv`` - flag to write event information to default CSV files in the current directory with default filenames
* ``--csv-file <FILEPATH>`` - write event information to a specific CSV file at the provided filepath


.. note::

    If there were no events found, a CSV file is not written to.


.. important::

    When using the ``--csv-file`` option, since different events can have different
    properties, the ``--event-name`` and ``--contract-name`` options must be specified. If querying for multiple
    events at the same time i.e. running the command without ``--event-name``, the ``--csv`` option should be used
    to generate separate default filenames for the different events.
