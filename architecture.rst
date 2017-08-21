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

Consumers of the data identify it by owner's public key and the path. It is
important that someone else doesn't submit reencryption keys for the same
path. So, at first, we should add digital signatures for hash(path + policy)
(using pycrypto library?). Then this signature and associated data will be
recorded on the blockchain so that it is publicly verifyable. The miners
have to accept only paths with valid signatures.
Public key should be used as a part of rekey address.
The scheme wouldn't work with anonimity on, so it will have to be redesigned
to be anonymous in later versions of the protocol.

Mapping in the rekey store:

    * pubkey -> hash(path) -> (rekey, algorithm)

The pubkey here is *not* the encryption key, it's a separate signing key.

Algorithms/libraries to use:

    * ECDSA (pycryptodome / pycrypto), secp256k1 curve
    * sha3 module for hash functions (let's be future-proof!)
      (included in standard hashlib with python3.6+)


Non-anonymous protocol
============================

Owner of the data has signing keypair sk_o/pk_o and encrypting keypair ske_o/pke_o.
ske_o = hash(sk_o)

The path can be a string or a tuple (where a string is equivalent to a tuple with length one).
An example of a tuple-path::

    path = ('/home', 'ubuntu', 'secret.txt')

When a path contains many elements in the tuple, one can share not only one file, but also whole directories.
If the PRE algorithm is not multihop+unidirectional (there is only one like that), the encryption keys for
files/directories are::

    key[i] = hmac(ske_o, '/'.join(path[:i]))

so, key[0] is the (private) key for whole /home, key[1] for /home/ubuntu etc.
When a file (or object) with `path` is encrypted, the owner generates a symmetric key for it,
encrypts it with every of key[i] and attaches to the file (or returns just keys if asked for).
When attached to the file, the encrypted symmetric keys are stored together with hashes of
paths and subpaths so that we can verify that this file is encrypted for the users of this path.

When a file or a directory is shared with someone with a key pair (sk_b/pk_b), the re-encryption
key is created for a path shared::

    rk = rekey(key[i], pk_b)

where key[i] is calculated in-place from the path, and rk might mean also all re-encryption shares
rather than just one rekey.

After the calculation, the rk is stored with the KMS network. It will be stored in the following
(hierarchical) persistent mapping::

    pk_o -> hash(pk_b, '/'.join(path[:i])) -> (rk, policy, algorithm, sign(hash + rk + policy + algorithm, pk_o))

The policy is signed by the owner's public key in order to protect from submitting by someone else.
In order to protect from submitting after being revoked, the signature can be saved on blockchain
when the policy is submitted and when revoked so that no one can use a replay attack to submit it
again (needs to be rethoght for anonymous protocol).

All the interactions are encrypted with each node's public key + symmetric key, so that nobody
except that node can see the rekey. It's usually one-time interaction over rpcudp, so public key
encryption would work faster than TLS would work.
