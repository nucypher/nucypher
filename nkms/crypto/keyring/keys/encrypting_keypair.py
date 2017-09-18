from nkms.crypto import default_algorithm, pre_from_algorithm


class EncryptingKeypair(object):
    def __init__(self, privkey_bytes=None):
        self.pre = pre_from_algorithm(default_algorithm)

        if not privkey_bytes:
            self.priv_key = self.pre.gen_priv(dtype='bytes')
        else:
            self.priv_key = privkey_bytes
        self.pub_key = self.pre.priv2pub(self.priv_key)

    def encrypt(self, data):
        return self.pre.encrypt(self.pub_key, data)
