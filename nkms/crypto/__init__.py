import importlib
from nacl.utils import random  # noqa

# Random 'g' parameter, perhaps, should be selected
# using some public value (such as hashMerkleRoot of Bitcoin genesis block)
# but since bbs98 is for tests anyway, having any random is good enough here
default_algorithm = dict(
        symmetric=dict(
            cipher='nacl'),
        pre=dict(
            cipher='bbs98',     # BBS98 is only temporary here, for development
            curve=714,          # secp256k1 in OpenSSL
            g=b'1:Axyxmlw2HrO+VcCXwxDQ02qqgexsKOZ6gDC6wy7zJB0X',
            m=None, n=None))


def symmetric_from_algorithm(algorithm):
    module = importlib.import_module(
            'nkms.crypto.block.' + algorithm['symmetric']['cipher'])
    # TODO need to cache this
    return module.Cipher


def pre_from_algorithm(algorithm):
    kw = {k: v for k, v in algorithm['pre'].items()
          if k != 'cipher' and v is not None}
    module = importlib.import_module(
            'nkms.crypto.pre.' + algorithm['pre']['cipher'])
    # TODO need to cache this
    return module.PRE(**kw)
