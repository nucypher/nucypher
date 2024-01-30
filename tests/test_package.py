

import builtins

import pytest

from nucypher.exceptions import DevelopmentInstallationRequired


class TestsImportMocker:

    REAL_IMPORT = builtins.__import__
    __active = False

    def mock_import(self, name, *args, **kwargs):
        if 'tests' in name and self.__active:
            raise ImportError
        return self.REAL_IMPORT(name, *args, **kwargs)

    def start(self):
        builtins.__import__ = self.mock_import
        self.__active = True

    def stop(self):
        builtins.__import__ = self.REAL_IMPORT
        self.__active = False

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


@pytest.fixture(scope='function')
def import_mocker():
    mock = TestsImportMocker()
    try:
        yield mock
    finally:
        mock.stop()


def test_use_vladimir_without_development_installation(import_mocker, mocker):

    # Expected error message (Related object)
    from tests.utils.middleware import EvilMiddleWare
    import_path = f'{EvilMiddleWare.__module__}.{EvilMiddleWare.__name__}'
    message = DevelopmentInstallationRequired.MESSAGE.format(importable_name=import_path)
    del EvilMiddleWare

    with import_mocker:
        from nucypher.characters.unlawful import Vladimir  # Import OK
        with pytest.raises(DevelopmentInstallationRequired, match=message):  # Expect lazy failure
            Vladimir.from_target_ursula(target_ursula=mocker.Mock())


def test_get_pyevm_backend_without_development_installation(import_mocker):

    # Expected error message (Related object)
    from tests import constants
    import_path = f'{constants.__name__}'
    message = DevelopmentInstallationRequired.MESSAGE.format(importable_name=import_path)
    del constants

    with import_mocker:
        from nucypher.blockchain.eth.providers import (
            _get_pyevm_test_backend,  # Import OK
        )
        with pytest.raises(DevelopmentInstallationRequired, match=message):     # Expect lazy failure
            _get_pyevm_test_backend()
