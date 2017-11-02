from nkms.keystore.db import Base
from sqlalchemy import Column, Integer, BigInteger, Binary


class Key(Base):
    __tablename__ = 'keys'

    id = Column(Integer, primary_key=True)
    fingerprint = Column(Binary(32), unique=True)
    key_data = Column(BigInteger, unique=True)
