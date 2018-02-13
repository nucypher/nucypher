import sha3

from nkms.keystore.db import Base
from sqlalchemy import Column, Integer, LargeBinary, ForeignKey
from sqlalchemy.orm import relationship


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(LargeBinary, unique=True)
    key_data = Column(LargeBinary, unique=True)

    policy = relationship("Policy", uselist=False, back_populates="policies")

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


class KeyFrag(Base):
    __tablename__ = 'keyfrags'

    id = Column(Integer, primary_key=True)
    key_frag = Column(LargeBinary, unique=True)

    policy = relationship("Policy", uselist=False, back_populates="policies")

    def __init__(self, key_frag):
        self.key_frag = key_frag


class Policy(Base):
    __tablename__ = 'policies'

    id = Column(Integer, primary_key=True)
    hrac = Column(LargeBinary, unique=True)
    alice_sig = Column(LargeBinary)
    keyfrag_id = Column(Integer, ForeignKey('keyfrags.id'))
    alice_pubkey_id = Column(Integer, ForeignKey('keys.id'))

    keyfrag = relationship("KeyFrag", back_populates="policies")
    alice_pubkey = relationship("KeyFrag", back_populates="policies")

    def __init__(self, hrac, alice_sig, keyfrag, alice_pubkey):
        self.hrac = hrac
        self.alice_sig = alice_sig
        self.keyfrag_id = keyfrag.id
        self.alice_pubkey_id = alice_pubkey.id
