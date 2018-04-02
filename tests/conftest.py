from .fixtures import *
from .eth_fixtures import *

from umbral.config import set_default_curve
from cryptography.hazmat.primitives.asymmetric import ec

set_default_curve(ec.SECP256K1())
