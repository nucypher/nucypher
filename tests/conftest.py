from cryptography.hazmat.primitives.asymmetric import ec
from umbral.config import set_default_curve
from .eth_fixtures import *
from .fixtures import *


set_default_curve(ec.SECP256K1())
