import sha3

from datetime import datetime
from nkms.keystore.db import Base
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


class PolicyContract(Base):
    __tablename__ = 'policycontracts'

    id = Column(Integer, primary_key=True)
    expiration = Column(DateTime)
    deposit = Column(LargeBinary)
    hrac = Column(LargeBinary, unique=True)
    key_frag = Column(LargeBinary, unique=True)
    alice_pubkey_sig_id = Column(Integer, ForeignKey('keys.id'))
    # alice_pubkey_enc_id = Column(Integer, ForeignKey('keys.id'))
    # bob_pubkey_sig_id = Column(Integer, ForeignKey('keys.id'))
    alice_signature = Column(LargeBinary, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, expiration, deposit, hrac,
                 key_frag, alice_pubkey_sig_id,
                 # alice_pubkey_enc_id, bob_pubkey_sig_id,
                 alice_signature):
        self.expiration = expiration
        self.deposit = deposit
        self.hrac = hrac
        self.key_frag = key_frag
        self.alice_pubkey_sig_id = alice_pubkey_sig_id
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
