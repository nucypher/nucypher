import nkms.db
import shutil
import os
import appdirs


def pytest_runtest_setup(item):
    # Monkey-patching for tests so that we don't overwrite the default db
    nkms.db.DB_NAME = 'debug-rekeys-db'


def pytest_runtest_teardown(item, nextitem):
    path = os.path.join(
            appdirs.user_data_dir(nkms.db.CONFIG_APPNAME), nkms.db.DB_NAME)
    if os.path.exists(path):
        shutil.rmtree(path)
