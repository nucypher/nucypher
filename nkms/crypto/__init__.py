import importlib
from nacl.utils import random  # noqa
from npre.curves import secp256k1

default_algorithm = dict(
        symmetric=dict(
            cipher='nacl'),
        pre=dict(
            cipher='bbs98',     # BBS98 is only temporary here, for development
            curve=secp256k1,
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
