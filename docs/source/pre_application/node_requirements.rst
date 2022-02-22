.. _node-requirements:

Node Requirements
=================

Minimum System Requirements
---------------------------

* Debian/Ubuntu (Recommended)
* 20GB storage
* 4GB RAM
* x86 architecture
* Static IP address
* Exposed TCP port 9151

Nodes can be run on cloud infrastructure - for example, a
`Digital Ocean 4GB Basic Droplet <https://www.digitalocean.com/pricing/>`_
satisfies the requirements listed above.

The above requirements only apply if you intend to run a node yourself.
Alternatively, a staking provider can run a node on your behalf.


PRE Node Configuration Requirements
-----------------------------------

Ethereum Node Provider URI
++++++++++++++++++++++++++

The PRE node will need to execute an initial transaction to confirm its
operation on startup, and therefore requires access to an
`ethereum node <https://web3py.readthedocs.io/en/stable/node.html>`_
(either a local or remote ethereum node) to broadcast the transaction. Remote
ethereum providers include Infura, Alchemy etc. and an HTTPS URI will need to
be configured (``https://<URI>``), whereas a local full node would entail running
`geth <https://geth.ethereum.org/>`_ locally and configured using the
IPC URI (``ipc://<PATH TO IPC FILE>``).
This value is specified via the ``--eth-provider`` CLI parameter.

It is worth noting that running a local ethereum node is quite the undertaking,
and has its own
`additional requirements <https://docs.ethhub.io/using-ethereum/running-an-ethereum-node/>`_.


Operator Software Ethereum Account
++++++++++++++++++++++++++++++++++

A software wallet is recommended for the PRE node operator's ethereum account
since the account needs to remain unlocked to execute an automated transaction
when the node first starts.

.. caution::

    - Operator accounts **do not** need NU/KEEP/T tokens for any reason; do not keep NU/KEEP/T in the
      operator account.
    - Do not store large amounts of ETH in the operator account; only enough to pay gas fees. Nodes
      only need to execute a single transaction on the first start which costs ~100K gas at
      a gas price of 146 gwei, this would be ~0.015 ETH). There are no subsequent transactions on restarts.
    - Store the operator account password in a password manager

To create a new ethereum software account using the ``geth`` CLI
(more information `here <https://geth.ethereum.org/>`_):

    .. code::

        geth account new

    - Never share your ethereum account password.
    - Do not forget your ethereum account password.
    - Secure your ethereum account password in a password manager.

This command will add a new account to your local keystore.


PRE Node Operator Transaction Signer
++++++++++++++++++++++++++++++++++++

In conjunction with an Ethereum node provider for broadcasting to the
Ethereum blockchain, the node also needs to configure a transaction signer
for signing messages to be broadcasted.

This separation of a transaction signer from an Ethereum node allows pre-signed
transactions to be sent to an external (possibly remote) ethereum node and is
particularly desirable when interacting with an untrusted ethereum node.

Local ethereum keystore signing can be configured for the operator software
account. Local keystore signing utilizes `eth-account <https://github.com/ethereum/eth-account/>`_
to sign ethereum transactions using local ethereum keystore files. By default
on Linux, the default local keystore directory path is ``~/.ethereum/keystore``.
The local keystore signer can be specified during initialization using the
following URI format, ``--signer`` CLI parameter and ``keystore://<PATH TO LOCAL KEYSTORE>`` as the
value, eg. ``--signer keystore:///root/.ethereum/keystore``.


.. note::

    The expectation is that the operator account is part of the local ethereum keystore.
