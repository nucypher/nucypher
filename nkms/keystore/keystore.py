from nkms.crypto import api as API


class KeyStore(object):
    """
    A storage class of cryptographic keys.
    """

    def __init__(self):
        """
        Initializes a KeyStore object.

        TODO: Actually store keys.
        TODO: Load keys from system.
        """
        pass

    def gen_ecies_keypair(self):
        """
        Generates an ECIES keypair.

        :return: ECIES encrypting keypair
        """
        pass

    def gen_ecdsa_keypair(self):
        """
        Generates an ECDSA keypair.

        :return ECDSA signing keypair
        """
        pass
