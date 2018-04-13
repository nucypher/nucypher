from cryptography.hazmat.primitives.asymmetric import ec
from umbral.config import set_default_curve
from .fixtures import *
from .eth_fixtures import *


set_default_curve(ec.SECP256K1())
