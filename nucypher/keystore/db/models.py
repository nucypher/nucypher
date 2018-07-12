import sha3

from datetime import datetime

from nucypher.crypto.utils import fingerprint_from_key
from nucypher.keystore.db import Base
from sqlalchemy.orm import relationship

from sqlalchemy import (
    Column, Integer, LargeBinary, ForeignKey, Boolean, DateTime
)


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(LargeBinary, unique=True)
    key_data = Column(LargeBinary, unique=True)
    is_signing = Column(Boolean, unique=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, fingerprint, key_data, is_signing):
        self.fingerprint = fingerprint
        self.key_data = key_data
        self.is_signing = is_signing

    @classmethod
    def from_umbral_key(cls, umbral_key, is_signing):
        fingerprint = fingerprint_from_key(umbral_key)
        key_data = bytes(umbral_key)
        return cls(fingerprint, key_data, is_signing)


class PolicyArrangement(Base):
    __tablename__ = 'policyarrangements'

    id = Column(LargeBinary, unique=True, primary_key=True)
    expiration = Column(DateTime)
    k_frag = Column(LargeBinary, unique=True, nullable=True)
    alice_pubkey_sig_id = Column(Integer, ForeignKey('keys.id'))
    alice_pubkey_sig = relationship(Key, backref="policies", lazy='joined')
    # alice_pubkey_enc_id = Column(Integer, ForeignKey('keys.id'))
    # bob_pubkey_sig_id = Column(Integer, ForeignKey('keys.id'))
    # TODO: Maybe this will be two signatures - one for the offer, one for the KFrag.
    alice_signature = Column(LargeBinary, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, expiration, id,
                 k_frag=None, alice_pubkey_sig=None,
                 # alice_pubkey_enc_id, bob_pubkey_sig_id,
                 alice_signature=None):
        self.expiration = expiration
        self.id = id
        self.k_frag = k_frag
        self.alice_pubkey_sig = alice_pubkey_sig
        # self.alice_pubkey_enc_id = alice_pubkey_enc_id
        # self.bob_pubkey_sig_id = bob_pubkey_sig_id
        self.alice_signature = alice_signature


class Workorder(Base):
    __tablename__ = 'workorders'

    id = Column(Integer, primary_key=True)
    bob_pubkey_sig_id = Column(Integer, ForeignKey('keys.id'))
    bob_signature = Column(LargeBinary, unique=True)
    hrac = Column(LargeBinary, unique=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, bob_pubkey_sig_id, bob_signature, hrac):
        self.bob_pubkey_sig_id = bob_pubkey_sig_id
        self.bob_signature = bob_signature
        self.hrac = hrac
