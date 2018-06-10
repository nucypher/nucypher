from nucypher.crypto.constants import PUBLIC_KEY_LENGTH, CAPSULE_LENGTH
from bytestring_splitter import BytestringSplitter
from umbral.config import default_params
from umbral.keys import UmbralPublicKey
from umbral.pre import Capsule


key_splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH))
capsule_splitter = BytestringSplitter((Capsule, CAPSULE_LENGTH, {"params": default_params()}))

