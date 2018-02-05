# WIP w/ hendrix@8227c4abcb37ee6d27528a13ec22d55ee106107f

from sqlalchemy.engine import create_engine

from nkms.characters import Ursula
from nkms.keystore import keystore
from nkms.keystore.db import Base

engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
ursulas_keystore = keystore.KeyStore(engine)
_URSULA = Ursula(urulsas_keystore=ursulas_keystore)
_URSULA.attach_server()

from hendrix.deploy.base import HendrixDeploy

deployer = HendrixDeploy("start", {"wsgi":_URSULA._rest_app, "http_port": 3500})
deployer.run()
