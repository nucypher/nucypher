import nkms.db
from nkms.db import DB
import shutil

# Monkey-patching for tests so that we don't overwrite the default db
nkms.db.DB_NAME = 'debug-rekeys-db'


def test_db():
    db = DB()
    db[b'x'] = b'y'
    assert db[b'x'] == b'y'
    db.close()

    db2 = DB()
    assert db2[b'x'] == b'y'
    db2.close()

    assert db.path == db2.path

    shutil.rmtree(db.path)
