import sha3

from nkms.keystore.db import Base
from sqlalchemy import Column, Integer, LargeBinary


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(LargeBinary, unique=True)
    key_data = Column(LargeBinary, unique=True)

    def __init__(self, key_data):
        self.key_data = key_data
        self.fingerprint = self.get_fingerprint()

    def get_fingerprint(self) -> bytes:
        """
        Hashes the key with keccak_256 and returns the hexdigest as a String.

        :param key_data: Actual key data to hash

        :return: Fingerprint of key as a string
        """
        return sha3.keccak_256(self.key_data[2:]).hexdigest().encode()
