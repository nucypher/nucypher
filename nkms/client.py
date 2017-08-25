from nkms.network import dummy


class Client(object):
    """
    Client which will be used by Python developers to interact with the
    decentralized KMS. For now, this is just the skeleton.


    We will support two capabilities: simple object encryption where a key for
    an object is given by its path, and attribute-based policy where there are
    multiple secrets corresponding to a path. Let's first describe API for
    simple object encryption.

    When doing simple object encryption, each path has a symmetric key encrypted
    with owner's public key (pub). Server works with encrypted symmetric key
    using low-level methods ending with _key, and client can do more high-level
    functions (such as decryption using this key or interaction with different
    storage backends).
    """
    network_client_factory = dummy.Client

    def __init__(self, conf=None):
        """
        :param str conf: Config file to load/save the key information from. If
            not given, a default one in the home directory is used
            or created
        """
        self._nclient = Client.network_client_factory()

    def encrypt_key(self, key, pubkey=None, path=None, algorithm=None):
        """
        Encrypt (symmetric) key material with our public key or the public key
        "pub" if given.

        If "path" is given, we encrypt "key" with derived private keys for each
        subpath and return msgpacked keys for all the subpaths. For example, a
        path could be:

        path = "/passwords/aws/mycoolwebsite.com"

        and for that, we have derived keys for "/", "/passwords",
        "/passwords/aws" and "/passwords/aws/mycoolwebsite.com". They all
        encrypt the same symmetric key "key".

        :param bytes key: Symmetric key to encrypt
        :param bytes pubkey: Public key to encrypt for
        :param tuple(str) path: Path to the data (to be able to share
            sub-paths). If None, encrypted with just our pubkey.
            If contains only 1 element or is a string, this is just used as a
            unique identifier w/o granular encryption.
        :param dict algorithm: Algorithm parameters (name, curve, re-encryption
            type, m/n etc). None if default

        :return: Encrypted key(s)
        :rtype: bytes
        """
        pass

    def decrypt_key(self, key, pubkey=None, path=None, owner=None):
        """
        Decrypt (symmetric) key material. Params similar to decrypt()
        """
        pass

    def grant(self, pubkey, path=None, policy=None):
        """
        Allow pubkey to read the data by path (or everything) by creating the
        re-encryption key and submitting it to the network.

        :param bytes pubkey: Public key of who we share the data with
        :param tuple(str) path: Path which we share. If None - share everything
        :param dict policy: Policy for sharing. For now, can have start_time and
            stop_time (in Python datetime or unix time (int)). Also permissions
            to 'read' the key, 'remove' the rekey and 'grant' permissions to
            others. When policy is not set, it's only 'read'
        """
        pass

    def revoke(self, pubkey, path=None):
        """
        Revoke a currently existing policy. Tells re-encryption nodes to remove
        the corresponding rekeys.

        :param bytes pubkey: Public key of who we shared the data with
        :param tuple(str) path: Path which we share. If None - revoke everything
        """
        pass

    def list_permissions(self, pubkey=None, path=None):
        pass

    def encrypt_bulk(self, data, key, algorithm=None):
        """
        Encrypt bulk of the data with a symmetric cipher

        :param bytes data: Data to encrypt
        :param bytes key: Symmetric key
        :param str algorithm: Algorithm to use or None for default

        :return: Encrypted data
        :rtype: bytes
        """
        pass

    def decrypt_bulk(self, edata, key, algorithm=None):
        """
        Decrypt bulk of the data with a symmetric cipher

        :param bytes edata: Data to decrypt
        :param bytes key: Symmetric key
        :param str algorithm: Algorithm to use or None for default

        :return: Plaintext data
        :rtype: bytes
        """
        pass

    def open(self, pubkey=None, path=None, mode='r', fd=None, algorithm=None):
        """
        The main interface through which Python API will work.

        One way is to open an encrypted file via the descriptor fd. Will
        internally use methods decrypt_key and decrypt_bulk.

        The other way is opening the actual file through backends and using the
        KMS to decrypt data (or create new keys). The path schema examples:

        s3://my_bucket/path/to/secret.txt
        ipfs://0x1242542346/path/file.txt
        file://home/ubuntu/my/secret/file.txt

        The mode will be in agreement to the granted permissions.

        If pubkey is not set, we're working on our own files.
        """
        pass

    def remove(self, pubkey=None, path=None):
        """
        Remove the file and all the rekeys associated with it. Similar to revoke
        but removing the actual files if the path is given with a schema.
        """
        pass

    def encrypt(self, data, path=None, algorithm=None):
        """
        Encrypts data in a form ready to ship to the storage layer.

        :param bytes data: Data to encrypt
        :param tuple(str) path: Path to the data (to be able to share
            sub-paths). If None, encrypted with just our pubkey.
            If contains only 1 element or is a string, this is just used as a
            unique identifier w/o granular encryption.
        :param dict algorithm: Algorithm parameters (name, curve, re-encryption
            type, m/n etc). None if default

        :return: Encrypted data
        :rtype: bytes
        """
        # Not needed if open() is there?
        pass

    def decrypt(self, edata, path=None, owner=None):
        """
        Decrypt data encrypted by its owner. If the owner != ourselves, a
        re-encryption request is automatically submitted. The function
        automatically splits out encrypted symmetric keys.

        :param bytes edata: Encrypted data
        :param tuple(str) path: Path to the data or its identifier
        :param bytes owner: If the path is None, owner can be used to identify
            the re-encryption key. The owner is specified by his pubkey

        :return: Unencrypted data
        :rtype: bytes
        """
        # Not needed if open() is there?
        pass
