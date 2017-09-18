


class KeyRing(object):
    def __init__(self, sig_keypair=None, enc_keypair=None):
        if not sig_keypair:
            # Generate signing keypair
            pass
        if not enc_keypair:
            # Generate encryption keypair
            pass
        self.sig_keypair = sig_keypair
        self.enc_keypair = enc_keypair
