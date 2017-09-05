import sys
import hashlib

if sys.version_info < (3, 6):
    import sha3


class KMAC_256(object):
    # TODO If performance is needed, this could be optimized a bit...
    # TODO Would be preferable to follow NIST and use cSHAKE.
    def __init__(self):
        self.LENGTH_BYTES = 32
        self.BLOCK_SIZE_BYTES = 136

    def _bytepad(self, x, w):
        # padded_x = w || x || {\x00...}
        padded_x = (w).to_bytes(2, byteorder='big') + x
        while len(padded_x) % w != 0:
            padded_x += b'\x00'
        return padded_x

    def digest(self, key, message):
        """
        Generates a KMAC (Keccak-MAC) from a key and message.

        :param bytes key: Key to use in KMAC construction.
        :param bytes message: Message to concat with the key during hashing.

        :return: Hashed KMAC digest
        :rtype: bytes
        """
        kmac = hashlib.shake_256()
        new_X = (self._bytepad(key, self.BLOCK_SIZE_BYTES)
                 + message
                 + (self.LENGTH_BYTES*8).to_bytes(2, byteorder='big'))

        kmac.update(new_X)
        return kmac.digest(self.LENGTH_BYTES)
