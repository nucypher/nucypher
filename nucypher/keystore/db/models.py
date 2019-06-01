"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, LargeBinary, ForeignKey, Boolean, DateTime
)
from sqlalchemy.orm import relationship

from nucypher.crypto.utils import fingerprint_from_key
from nucypher.keystore.db import Base


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(LargeBinary, unique=True)
    key_data = Column(LargeBinary, unique=True)
    is_signing = Column(Boolean, unique=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, fingerprint, key_data, is_signing) -> None:
        self.fingerprint = fingerprint
        self.key_data = key_data
        self.is_signing = is_signing

    def __repr__(self):
        return f'{self.__class__.__name__}(id={self.id})'

    @classmethod
    def from_umbral_key(cls, umbral_key, is_signing):
        fingerprint = fingerprint_from_key(umbral_key)
        key_data = bytes(umbral_key)
        return cls(fingerprint, key_data, is_signing)


class PolicyArrangement(Base):
    __tablename__ = 'policyarrangements'

    id = Column(LargeBinary, unique=True, primary_key=True)
    expiration = Column(DateTime)
    kfrag = Column(LargeBinary, unique=True, nullable=True)
    alice_verifying_key_id = Column(Integer, ForeignKey('keys.id'))
    alice_verifying_key = relationship(Key, backref="policies", lazy='joined')

    # TODO: Maybe this will be two signatures - one for the offer, one for the KFrag.
    alice_signature = Column(LargeBinary, unique=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self,
                 expiration,
                 id,
                 kfrag=None,
                 alice_verifying_key=None,
                 alice_signature=None
                 ) -> None:

        self.expiration = expiration
        self.id = id
        self.kfrag = kfrag
        self.alice_verifying_key = alice_verifying_key
        self.alice_signature = alice_signature

    def __repr__(self):
        return f'{self.__class__.__name__}(id={self.id})'


class Workorder(Base):
    __tablename__ = 'workorders'

    id = Column(Integer, primary_key=True)
    bob_verifying_key_id = Column(Integer, ForeignKey('keys.id'))
    bob_signature = Column(LargeBinary, unique=True)
    arrangement_id = Column(LargeBinary, unique=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __init__(self, bob_verifying_key_id, bob_signature, arrangement_id) -> None:
        self.bob_verifying_key_id = bob_verifying_key_id
        self.bob_signature = bob_signature
        self.arrangement_id = arrangement_id

    def __repr__(self):
        return f'{self.__class__.__name__}(id={self.id})'
