NuCypher decentralized KMS
============================

Depencencies / technologies
=============================

* Python 3.5+
* asyncio
* rpcudp - python3.5 branch
* kademlia - python3.5 branch
* ZODB for persistence
* keas.kmi as an example how to have persistent encrypted objects
* C bindings to OpenSSL for encryption (?)
* PyCryptodome / PyCrypto for symmetric block ciphers
* buildout for building (more convenient when using custom git dependencies?)

Decentralized network
========================

Kademlia by default (see kademlia.network.server) saves data in multiple nodes,
and also clients are servers there.

We need to split up client and server (that is, get and set methods of the
client don't save data in the current node).

In the first version of the protocol, we will use m-of-n threshold re-encryption
for ECIES. It means, that instead of one re-encryption key, we will generate
n re-encryption keys and store each with one node in the network.

By default, Kademlia stores data *copied* to *several* closest nodes. Instead,
we want find n closest and responding nodes and store rekeys with them, w/o
duplicating. The methods get() and set() in `kademlia.network.Server` are to
be used only as documentation. We will have to write our own ClientServer class.

The protocol (`kademlia.protocol.KademliaProtocol`) is also to be re-written for
reencryption rather than returning data.
When connections are established with nodes, they should tell their pubkeys
(or rather the pubkeys should be used as public nodeids).

New methods should include: `store_rekey` (with policy), `reencrypt`,
`remove_rekey`.

Nodes should be able to have information on how long they can store
re-encryption keys for (this information will come from metadata written
on blockchain). Clients will be able to knows in advance.
Each node is identified by its pubkey, and clients will be able to know
in advance which node is available to store the policy for long enough.

Another feature to be implemented here is replicating all the rekeys to a
different node is the node is going to be offline for a long time
(complete shutdown). If this happens, the node passes all its rekeys
to node(s) which are capable to handle them for long enough, and write
this information on blockchain.

When a node start, a key which will be used to decrypt the persisted
data can be generated, read from a file (not very safe!), made from
passphrase (safe if the passphrase is long enough and generated),
or stored + delegated access using our KMS itself.

This kademlia-based protocol is *not* intended to be anonymous, we hope for
split-key reencryption properties (e.g. that < m random nodes will be corrupt).

Persistence layer
====================

The persistence layer to be used is ZODB. We can also take encrypted objects
feature from keas.kmi.
Current ZODB uses asyncio also, so we need to use common event loop for both
ZODB and kademlia.
ZODB can just use FileStorage rather than ZEO when working in a single-process
regime, and we can use ZEO + clients for multiple CPU cores. But for simplicity,
we can start with just FileStorage (which, although, can be described in a zcml
config)

API
=====
First, we create a Python API. This API should allow to:

* generate a new random symmetric key (this is usually implicit)
* encrypt (off-chain, but store meta-information with files)
* grant and revoke access (on chain)
* decrypt_key (query the network)
* decrypt (data using a key from decrypt_key)

also we can have similar functions for signing rather than just
encryption/decryption in the next versions.

The API should be implemented for: Python (native client),
JSON server (localhost, similar to bitcoind), Javascript (native).

Encryption
=============
We should be able to have algorithms pluggable, so we will note which algo
did we use for pubkey encryption / reencryption in a rekey meta-information.
The choices are:

* Normal BBS98 (1-of-n) (debug only);
* Normal ECIES (1-of-n);
* AFGH (n-of-n) (debug only);
* Split-key ECIES (m-of-n, production ready).

As soon as split-key ECIES is available, we immediately switch to it.
The curve should also be specified. Makes sense to use secp256k1 as it was
well tested with Bitcoin.

We also store which block cipher we used. The choices are:

* AES256-GCM (lisodium-based library for zerodb is the fastest?)
* Other AES modes (maybe not vulnerable to reusing the IV)
* Salsa20 from libsodium
