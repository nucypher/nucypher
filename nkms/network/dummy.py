from nkms.db import DB
from nkms import crypto


class Client(object):
    """
    This is a dummy client which doesn't connect anywhere and just does
    re-encryptions. Needed only for tests and development. NOT for any real
    usage.

    Any client (dummy or not) should work similarly to ZEO client which runs in
    an asyncio event loop in a thread transparently. When user instantiates the
    class, a new thread with an event loop starts, and all the methods block.

    There is a _server attribute which is an async client=server (similar to
    that in kademlia).

    Initially, it is implemented here w/o networking or event loops, in a sync
    manner.
    """

    def __init__(self, **kw):
        # Dummy client stores in lmdb
        # in the actual network it should be done on the server
        self._storage = DB()

    def store_rekeys(self, pub, k, rekeys, algorithm):
        """
        :param bytes pub: Public (signing) key
        :param bytes k: ID for the rekeys (or key in a key-value store sense)
        :param tuple rekeys: Rekeys to store. If bytes, it's just one rekey. If
            a tuple or a list of length > 1 - m-of-n reencryption is used.
        :param dict algorithm: Parameters of the re-encryption algo
        :param bytes sig: Digital signature of hash(k, metainfo)
        """
        if type(rekeys) in (list, tuple):
            if len(rekeys) > 1:
                raise NotImplementedError(
                        'm-of-n reencryption not yet available')
            rekeys = rekeys[0]
        # Should specify and check signature also
        self._storage[k] = {b'rk': rekeys, b'algorithm': algorithm}

    def remove_rekeys(self, pub, k):
        # Should specify and check signature also
        del self._storage[k]

    def reencrypt(self, pub, k, ekey):
        """
        :param bytes pub: Public (signing) key
        :param bytes k: Address of the rekey derived from the path/pubkey
        :param bytes ekey: Encrypted symmetric key to reencrypt
        """
        rekey = self._storage[k][b'rk']
        algorithm = self._storage[k][b'algorithm']
        pre = crypto.pre_from_algorithm(algorithm)
        return pre.reencrypt(rekey, ekey)

    def close(self):
        """
        Disconnect from the network. In the dummy class - nothing here
        """
        pass
