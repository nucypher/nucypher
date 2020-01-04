from nucypher.characters.lawful import Enrico
from nucypher.config.storages import ForgetfulNodeStorage


def test_initing_causes_cert_deletion(enacted_federated_policy):
    """
    This is a strange test.  It shows #1554 - that rapid Character instantiation causes
    the __del__ of a node storage object to be run, which in turn improperly deletes certificates.
    """
    class IncorrectDeletionLogic:
        """
        A flag to stand in for deletion of a directory of certificates (well, actually, all node metadata).
        """
        called_ever = False

    def bad_deletion(*args, **kwargs):
        IncorrectDeletionLogic.called_ever = True

    ForgetfulNodeStorage.__del__ = bad_deletion

    """
    Now the weird part.  If we create several (around 10) Characters without is_me in rapid succession, the ForgetfulNodeStorage object's __del__ is called.
    It's not always for the same reason; sometimes it appears to be related to the context switching
    of OpenSSL, while other times it seems to be the deletion of the reference when we append
    the node_storage_function to the node class.
    It doesn't really matter *why* it happens - it's clear that the __del__ of a class which
    is later composed on a Character class which is repeatedly instantiated can't really be used
    to clean up the filesystem.
    """
    for i in range(12):
        Enrico(policy_encrypting_key=enacted_federated_policy.public_key)

    assert IncorrectDeletionLogic.called_ever
