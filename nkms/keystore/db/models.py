import sha3

from nkms.keystore.db import Base
from sqlalchemy import Column, Integer, BigInteger, LargeBinary


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(LargeBinary(64), unique=True)
    key_data = Column(BigInteger, unique=True)

    def __init__(self, key_data):
        self.fingerprint = Key.get_fingerprint(key_data)
        self.key_data = key_data

    @classmethod
    def get_fingerprint(cls, key_data: bytes) -> str:
        """
        Hashes the key with keccak_256 and returns the hexdigest as a String.

        :param key_data: Actual key data to hash

        :return: Fingerprint of key as a string
        """
        return sha3.keccak_256(key_data).hexdigest()
