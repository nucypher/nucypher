from nkms.crypto.constants import PUBLIC_KEY_LENGTH, CAPSULE_LENGTH
from nkms.crypto.utils import BytestringSplitter
from umbral.keys import UmbralPublicKey
from umbral.umbral import Capsule

key_splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH, {"as_b64": False}))
capsule_splitter = BytestringSplitter((Capsule, CAPSULE_LENGTH))