import base64
import msgpack
from nkms import crypto
from npre.bbs98 import PRE as BasePRE


def convert_priv(sk):
    return b'0:' + base64.encodebytes(sk).strip()


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
        priv_to = crypto.random(self.KEY_SIZE)
        rk = self.rekey(convert_priv(priv1), convert_priv(priv_to), dtype=bytes)
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
        emsg_l = msgpack.unpack(emsg)
        if emsg_l[0] == 2:
            _, priv, emsg = emsg_l
        return super(PRE, self).decrypt(priv, emsg, padding=padding)
