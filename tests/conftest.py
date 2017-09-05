import nkms.db


def pytest_runtest_setup(item):
    # Monkey-patching for tests so that we don't overwrite the default db
    nkms.db.DB_NAME = 'debug-rekeys-db'
