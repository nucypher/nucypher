import builtins
import pytest

from nucypher.exceptions import DevelopmentInstallationRequired


def test_development_install_required(capsys, mocker):
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if 'tests' in name:
            raise ImportError
        return real_import(name, *args, **kwargs)

    # Test lazy imports for entities that depends on the tests package
    try:
        builtins.__import__ = mock_import

        # For example...
        from nucypher.characters.unlawful import Vladimir     # Import OK
        with pytest.raises(DevelopmentInstallationRequired):  # Lazy Action
            Vladimir.from_target_ursula(target_ursula=mocker.Mock())

        from nucypher.blockchain.eth.providers import _get_pyevm_test_backend
        with pytest.raises(DevelopmentInstallationRequired):
            _get_pyevm_test_backend()

        from nucypher.characters.control.controllers import JSONRPCController
        with pytest.raises(DevelopmentInstallationRequired):
            JSONRPCController.test_client(self=mocker.Mock())

    finally:
        builtins.__import__ = real_import
