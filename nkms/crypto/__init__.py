import base64
import importlib
from nacl.utils import random  # noqa

# hashMerkleRoot for Bitcoin genesis block
_bitcoin_genesis = base64.encodebytes(bytes.fromhex(
    '4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b')).strip()

default_algorithm = dict(
        symmetric=dict(
            cipher='nacl'),
        pre=dict(
            cipher='bbs98',     # BBS98 is only temporary here, for development
            curve=714,          # secp256k1 in OpenSSL
            g=b'1:' + _bitcoin_genesis,
            m=None, n=None))


def symmetric_from_algorithm(algorithm):
    module = importlib('nkms.crypto.block.' + algorithm['symmetric']['cipher'])
    # TODO need to cache this
    return module.Cipher


def pre_from_algorithm(algorithm):
    kw = {k: v for k, v in algorithm['pre'].items()
          if k != 'cipher' and v is not None}
    module = importlib('nkms.crypto.block.' + algorithm['pre']['cipher'])
    # TODO need to cache this
    return module.PRE(**kw)
