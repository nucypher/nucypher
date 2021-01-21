.. _using-eth-node:

======================
Using an Ethereum Node
======================

For operations that require an ethereum provider for transaction signing and broadcasting, either a local or remote
ethereum node may be used. For general background information about choosing a node technology and operation,
see https://web3py.readthedocs.io/en/stable/node.html.


Local Ethereum Node
~~~~~~~~~~~~~~~~~~~

This is the typical configuration for a locally operated trusted ethereum node. For detailed information on using the
geth CLI and Javascript console, see https://geth.ethereum.org/interface/Command-Line-Options.

Assuming you have ``geth`` installed, to run a `geth` node in *fast* syncing mode:

.. code:: bash

   $ geth

and to run a Geth node in *light* syncing mode:

.. code:: bash

   $ geth --syncmode light

.. note::

    ``--syncmode light`` is not 100% stable.


If you want to use your hardware wallet, just connect it to your machine, and you'll see something like this in logs:

.. code:: bash

    INFO [08-30|15:50:39.153] New wallet appeared      url=ledger://0001:000b:00      status="Ethereum app v1.2.7 online"

If you see something like ``New wallet appeared, failed to open`` in the logs,
you need to reconnect the hardware wallet (without turning the ``geth`` node
off).

If you don't have a hardware wallet, you can create a software one. Whilst running the initialized node:

* Linux:

    .. code:: bash

        $ geth attach /home/<username>/.ethereum/geth.ipc
        > personal.newAccount();
        > eth.accounts
        ["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]

* MacOS:

    .. code:: bash

        $ geth attach /Users/<username>/Library/Ethereum/geth.ipc
        > personal.newAccount();
        > eth.accounts
        ["0x287a817426dd1ae78ea23e9918e2273b6733a43d"]

Where ``0x287a817426dd1ae78ea23e9918e2273b6733a43d`` is your newly created
account address and ``<username>`` is your user.

.. note::

    The Geth console **does not return EIP-55 compliant checksum addresses**, and instead will output
    the *lowercase* version of the address.  Since Nucypher requires EIP-55 checksum addresses, you will need
    to convert your address to checksum format:

    .. code:: javascript

       > web3.toChecksumAddress(eth.accounts[0])
       "0x287A817426DD1AE78ea23e9918e2273b6733a43D"


Run Geth with Docker
********************

Run a local geth using volume bindings:

.. code:: bash

    docker run -it -p 30303:30303 -v ~/.ethereum:/root/.ethereum ethereum/client-go

For alternate geth configuration via docker see:
`Geth Docker Documentation <https://geth.ethereum.org/docs/install-and-build/installing-geth#run-inside-docker-container>`_.



Remote Ethereum Node
~~~~~~~~~~~~~~~~~~~~

Nucypher supports remote ethereum providers such as Alchemy, Infura, Public Remote Node, but an external transaction
signing client is needed separate from the broadcasting node.


External Transaction Signing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In conjunction with an ethereum provider, an external transaction signer can be specified and operated
independently of the provider/broadcaster. This separation allows pre-signed transactions to be sent to an
external (possibly remote) ethereum node and is particularly desirable when interacting with an untrusted
ethereum node.

For example, external signers can be used with:

- Infura/Alchemy/Etc.
- Local ethereum node
- Remote ethereum node

The following external signers are currently supported:

#. :ref:`Hardware Wallet <signing-with-hardware>` (recommended for :ref:`Stakers <staking-guide>`)
#. :ref:`Clef <signing-with-clef>`
#. :ref:`Local Keystore <signing-with-local-keystore>` (recommended for :ref:`Workers <ursula-config-guide>`)

.. important::

    External signing support is an experimental feature and under active development.


.. _signing-with-hardware:

Signing with Hardware Wallet
****************************

A hardware wallet stores private keys on a physical device. Storing private keys offline keeps them out of
reach of attackers and therefore provides a high level of security.

.. note::

    Currently, ``nucypher`` only provides native support for Trezor. Work is underway to natively support other
    hardware wallets such as Ledger. In the meantime, other hardware wallets can be used in conjunction
    with `Clef <Signing with Clef>`_.

Trezor
++++++

A `Trezor <https://trezor.io/>`_ signer can be specified either through the CLI (``--signer``) or
API (``nucypher.blockchain.eth.signers.Signer.from_signer_uri``), using the URI ``trezor``.


.. _signing-with-clef:

Signing with Clef
*****************

Clef enables applications to connect to an ethereum node and send locally signed
transactions to be broadcasted. More
information about Clef can be found `here <https://geth.ethereum.org/docs/clef/tutorial>`_. Clef can
use hardware wallets (Ledger and Trezor) over USB, or geth formatted private keys by specifying the keystore
directory path.


Clef Setup
++++++++++

Clef is typically installed alongside geth.

.. important::

    Geth version 1.9.22 or higher is required.

If you already have geth installed on your system you may already have Clef installed.  To check for an
existing installation run:

.. code:: bash

    $ clef --version
    Clef version 0.0.0

If ``clef`` was not found, upgrade ``geth`` to the latest version and try again.

Next, initialize Clef with your chosen password to encrypt the master seed:

.. code:: bash

    $ clef init
    ...
    The master seed of clef will be locked with a password.
    Please specify a password. Do not forget this password!
    Password:


Running Clef
++++++++++++

.. code:: bash

    $ clef --keystore <PATH TO KEYSTORE> --chainid <CHAIN ID> --advanced


* ``<PATH TO KEYSTORE>`` - The path to the directory containing geth-formatted private key files; the default path for Linux is ``~/.ethereum/keystore``.
  **No need to specify if using a hardware wallet.**
* ``<CHAIN ID>`` - 1 is specified to ensure Clef signs transactions with the network ID of ethereum mainnet (4 for the ``ibex`` testnet on rinkeby).

.. code:: bash

    Enter 'ok' to proceed:
    > ok
   ...

    ------- Signer info -------
    * extapi_version : 6.0.0
    * extapi_http : n/a
    * extapi_ipc : <CLEF IPC PATH>
    * intapi_version : 7.0.0

where ``<CLEF IPC PATH>``:

    * Linux: ``/home/<username>/.clef/clef.ipc``
    * MacOS: ``/Users/<username>/Library/Signer/clef.ipc``


.. _clef-rules:

Clef Rules
++++++++++

By default, all requests to the Clef signer require manual confirmation. To overcome this, Clef allows the
configuration of rules to automate the confirmation of requests to the signer. In particular, we recommend that users
of a Clef signer with ``nucypher`` define the following rules file (``rules.js``), which simply approves the
listing of accounts:

.. code:: javascript

    function ApproveListing() {
        return "Approve"
    }

The sha256 digest of this particular 3-line file is ``8d089001fbb55eb8d9661b04be36ce3285ffa940e5cdf248d0071620cf02ebcd``.
We will use this digest to attest that we trust these rules:

.. code:: bash

    $ clef attest 8d089001fbb55eb8d9661b04be36ce3285ffa940e5cdf248d0071620cf02ebcd

    WARNING!

    Clef is an account management tool. It may, like any software, contain bugs.

    Please take care to
    - backup your keystore files,
    - verify that the keystore(s) can be opened with your password.

    Clef is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
    without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
    PURPOSE. See the GNU General Public License for more details.

    Enter 'ok' to proceed:
    > ok

    Decrypt master seed of clef
    Password:
    INFO [04-14|02:00:54.740] Ruleset attestation updated    sha256=8d089001fbb55eb8d9661b04be36ce3285ffa940e5cdf248d0071620cf02ebcd


Once the rules file is attested, we can run Clef with the ``--rules rules.js`` flag,
to indicate which are the automated rules (in our case, allowing the listing of accounts):

.. code:: bash

    $ clef --keystore <PATH TO KEYSTORE> --chainid <CHAIN ID> --advanced --rules rules.js


Usage
+++++

Once ``clef`` is running, specify the Clef signer either through the CLI (``--signer``) or
API (``nucypher.blockchain.eth.signers.Signer.from_signer_uri``), using the URI ``clef://<CLEF IPC PATH>``.


.. _signing-with-local-keystore:

Signing with Local Keystore
***************************

.. important::

    For operational security, the Keystore signer is not recommended for :ref:`Staker operations <staking-guide>`.
    An exception can be made for testnets, but Staker operations should be performed using a hardware wallet.

Local keystore signing utilizes `eth-account <https://github.com/ethereum/eth-account>`_ to sign ethereum transactions
using local ethereum keystore files. By default on Linux, the keystore directory path is ``~/.ethereum/keystore``
(on MacOS for Rinkeby testnet, ``/Users/<username>/Library/Ethereum/rinkeby/keystore``).


Usage
+++++

Specify the local keystore signer either through the CLI (``--signer``) or API (``nucypher.blockchain.eth.signers.Signer.from_signer_uri``),
using the URI ``keystore://<PATH TO LOCAL KEYSTORE>``.

The path provided can either be a directory of keystore files or an individual keystore file. In the case of a
directory, it is scanned and each of the keystore files contained are processed.
