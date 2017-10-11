import msgpack
from nkms.crypto import api
from npre.bbs98 import PRE as BasePRE


def convert_priv(sk):
    return b'\x00' + sk


class PRE(BasePRE):
    """
    Public key based single-hop version of BBS98.
    """
    KEY_SIZE = 32

    def priv2pub(self, priv):
        """
        Private key isa pure 32-bytes random number
        """
        if type(priv) is str:
            priv = priv.encode()
        if type(priv) is bytes:
            priv = convert_priv(priv)
        return super(PRE, self).priv2pub(priv)

    def rekey(self, priv1, pub2):
        priv_to = api.secure_random(self.KEY_SIZE)
        rk = super(PRE, self).rekey(
                convert_priv(priv1), convert_priv(priv_to), dtype=bytes)
        epriv_to = self.encrypt(pub2, priv_to)
        return msgpack.dumps([rk, epriv_to])

    def reencrypt(self, rekey, emsg):
        rk, epriv = msgpack.loads(rekey)
        remsg = super(PRE, self).reencrypt(rk, emsg)
        return msgpack.dumps([2, epriv, remsg])  # type 2 emsg

    def decrypt(self, priv, emsg, padding=True):
        # This is non-optimal b/c of double-deserialization
        # but this cipher is for development/tests, not production
        # so be it
        emsg_l = msgpack.loads(emsg)
        if emsg_l[0] == 2:
            _, epriv_to, emsg = emsg_l
            priv_to = self.decrypt(priv, epriv_to)
            priv = priv_to
        return super(PRE, self).decrypt(
                convert_priv(priv), emsg, padding=padding)
