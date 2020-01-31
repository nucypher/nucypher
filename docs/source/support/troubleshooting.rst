===============
Troubleshooting
===============


self.InsufficientTokens(f"Insufficient token balance ({self.token_agent})
-------------------------------------------------------------------------

There is an insufficient amount of NU in your staking account.


ValueError: {'code': -32000, 'message': 'no suitable peers available'}
----------------------------------------------------------------------

This is a geth error and not related to ``nucypher``. You are probably running a light node that needs
full nodes willing to serve information to it, but no such nodes were found (a frequent problem on the Goerli Ethereum testnet).


nucypher.blockchain.eth.interfaces.ConnectionFailed: Connection Failed, is IPC enabled
--------------------------------------------------------------------------------------

The provider URI may be incorrect.

For example: if the scheme is ``ipc://`` then the path should be appended as is to the end ``ipc:///home/…``
i.e. **THREE** slashes not two.


nucypher.config.base.OldVersion: Configuration file is the wrong version. Expected version 1; Got version UNKNOWN_VERSION
-------------------------------------------------------------------------------------------------------------------------

This is an issue with upgrading from a previous version while still having an older configuration on-disk.


Validation error: 'code': -32000, 'message': 'gas required exceeds allowance (8000000) or always failing transaction
--------------------------------------------------------------------------------------------------------------------

This error can be caused by a variety of reasons. Each time ``require()`` fails to validate a condition in a contract
without a corresponding check in the ``nucypher`` client itself, this error is raised. Over time, as we update the
client, this generic error will become extinct.

In the most common case:

- Ensure that your worker is `bonded to a staker <https://docs.nucypher.com/en/latest/guides/staking_guide.html#bond-an-ursula-to-a-staker>`_.
  You can confirm by running ``nucypher stake list`` and check that Worker is set correctly i.e. not ``0x0000``.


builtins.ValueError: {'code': -32000, 'message': 'insufficient funds for gas * price + value'}
----------------------------------------------------------------------------------------------

The Ursula node does not have enough (Goerli) ETH to pay for transaction gas. Ensure that your worker address has
(Goerli) ETH in it.


Warning! Error encountered during contract execution [Out of gas]
-----------------------------------------------------------------

The Ursula node does not have enough (Goerli) ETH to pay for transaction gas; ensure that your worker address has (Goerli) ETH in it.


RuntimeError: Click will abort further execution because Python 3 was configured to use ASCII as encoding for the environment
-----------------------------------------------------------------------------------------------------------------------------

Try setting the following environment variables:

.. code::

    export LC_ALL=en_US.utf-8
    export LANG=en_US.utf-8


builtins.FileNotFoundError: [Errno 2] No such file or directory: '/<path>/.cache/nucypher/log/nucypher.log.20191227'
--------------------------------------------------------------------------------------------------------------------

This is an artifact of upgrading Ursula - remove the directory ``<path>/.cache/nucypher/log`` and restart Ursula.


web3.exceptions.BadFunctionCallOutput: Could not transact with/call contract function, is contract deployed correctly and chain synced?
---------------------------------------------------------------------------------------------------------------------------------------

This error usually means your blockchain data is not synced.

If using geth, ensure that geth is fully synced. You can run ``geth --goerli --exitwhensynced`` which causes geth
to exit once fully synced.


ValueError: {'code': -32000, 'message': 'could not decrypt key with given password'}
------------------------------------------------------------------------------------

You are using the wrong password for your ethereum account.
