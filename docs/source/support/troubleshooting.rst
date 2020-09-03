===============
Troubleshooting
===============


self.InsufficientTokens(f"Insufficient token balance ({self.token_agent})
-------------------------------------------------------------------------

There is an insufficient amount of NU in your staking account.


ValueError: {'code': -32000, 'message': 'no suitable peers available'}
----------------------------------------------------------------------

This is a Geth error and not related to ``nucypher``. You are probably running a light node that needs
full nodes willing to serve information to it, but no such nodes were found (a frequent problem on the Ethereum testnets).


nucypher.blockchain.eth.interfaces.ConnectionFailed: Connection Failed, is IPC enabled
--------------------------------------------------------------------------------------

The provider URI may be incorrect.

For example: if the scheme is ``ipc://`` then the path should be appended as is to the end ``ipc:///home/…``
i.e. **THREE** slashes not two.


Validation error: 'code': -32000, 'message': 'gas required exceeds allowance (8000000) or always failing transaction
--------------------------------------------------------------------------------------------------------------------
This is a generic exception thrown by Geth meaning "Transaction Failed".
This error can be caused by a variety of reasons. Each time ``require()`` fails to validate a condition in a contract
without a corresponding check in the ``nucypher`` client itself, this error is raised. Over time, as we update the
client, this generic error will become extinct.

In the most common cases:

- Ensure that your worker is :ref:`bonded to a staker <bond-worker>`.
  You can confirm by running ``nucypher stake list`` and check that `Worker` is set correctly i.e. not ``0x0000``.
- If your worker is configured, ensure that the worker address has ETH and that the correct worker address is
  provided in the Ursula configuration file. You can view worker configuration by running ``nucypher ursula config``


builtins.ValueError: {'code': -32000, 'message': 'insufficient funds for gas * price + value'}
----------------------------------------------------------------------------------------------

The Ursula node does not have enough ETH to pay for transaction gas. Ensure that your worker address has ETH.


Warning! Error encountered during contract execution [Out of gas]
-----------------------------------------------------------------

The Ursula node does not have enough ETH to pay for transaction gas; ensure that your worker address has ETH.


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

If using Geth, ensure that Geth is fully synced. You can use the ``--exitwhensynced`` flag which causes Geth
to exit once fully synced.

When using parity in light mode, this is raised when the light node cannot satisfy the call/transaction, e.g. not
enough full nodes are serving requests.


ValueError: {'code': -32000, 'message': 'could not decrypt key with given password'}
------------------------------------------------------------------------------------

Potential reasons:

    #. You may be using the wrong password for your ethereum account.

    #. You may be using the wrong ethereum account.

    #. If trying to collect rewards, this is a `known bug <https://github.com/nucypher/nucypher/issues/1657>`_ in our
       code - rerun the command without the ``--staking-address`` option.


ValidationError: The field extraData is 97 bytes, but should be 32. It is quite likely that you are connected to a POA chain
----------------------------------------------------------------------------------------------------------------------------

Add the ``--poa`` flag to your command and try again.


ValueError: {'code': -32601, 'message': 'the method web3_clientVersion does not exist/is not available'}
--------------------------------------------------------------------------------------------------------

Ensure that the intended *signer* used is not mistakenly specified as a *provider*.

To view your existing ``nucypher`` configuration

.. code:: bash

    nucypher stake config

and to update values

.. code:: bash

    nucypher stake config --signer <SIGNER PATH> --provider <YOUR PROVIDER URI>
