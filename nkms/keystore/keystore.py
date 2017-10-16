from nkms.keystore import keypairs


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

    def gen_ecies_keypair(self, gen_priv=True) -> keypairs.EncryptingKeypair:
        """
        Generates an ECIES keypair.

        TODO: Initalize keypair with provided data.

        :param gen_priv: Generate private key or not?

        :return: ECIES encrypting keypair
        """
        ecies_keypair = keypairs.EncryptingKeypair()
        if gen_priv:
            ecies_keypair.gen_privkey()
        return ecies_keypair

    def gen_ecdsa_keypair(self, gen_priv=True) -> keypairs.SigningKeypair:
        """
        Generates an ECDSA keypair.

        TODO: Initalize keypair with provided data.

        :param gen_priv: Generate private key or not?

        :return ECDSA signing keypair
        """
        ecdsa_keypair = keypairs.SigningKeypair()
        if gen_priv:
            ecdsa_keypair.gen_privkey()
        return ecdsa_keypair

    def get_key(self):
        """
        Returns a key from the KeyStore.

        TODO: Implement this.
        TODO: Retrieve key by KeyID.
        """
        pass

    def add_key(self):
        """
        Adds a key to the KeyStore.

        TODO: Implement this.
        TODO: Maybe make an abstract base class for Keypair?
        """
        pass

    def del_key(self):
        """
        Deletes a key from the KeyStore.

        TODO: Implement this.
        TODO: Delete key by KeyID.
        """
        pass
